"""Fixed-source HIPRTC owner for additive FGMRES checkpoint history.

The two-symbol module initializes the pair of history blobs and captures one
committed restart row after a recurrence-v2 ``CHECKPOINT_FINALIZE`` launch.
It does not modify the frozen recurrence module or solve-record ABI.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, replace
from pathlib import Path
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

from .fgmres_checkpoint_history_plan_v1 import (
    HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1,
    HIP_FGMRES_CHECKPOINT_HISTORY_BLOCK_SIZE_V1,
    hip_fgmres_checkpoint_history_blob_abi_payload_v1,
)
from .fgmres_plan import HIP_FGMRES_MAX_ITERATIONS


HIP_RTC_FGMRES_CHECKPOINT_HISTORY_IDENTITY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-rtc-fgmres-checkpoint-history-identity.v1"
)
HIP_RTC_FGMRES_CHECKPOINT_HISTORY_ABI_VERSION_V1 = 1
HIP_RTC_FGMRES_CHECKPOINT_HISTORY_KERNEL_NAME_V1 = (
    "engine_v2_fgmres_checkpoint_history_v1"
)
HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1 = (
    "engine_v2_fgmres_checkpoint_history_initialize_v1"
)
HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1 = (
    "engine_v2_fgmres_checkpoint_history_capture_v1"
)

_SOURCE_RESOURCE = "kernels/engine_v2_fgmres_checkpoint_history_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17", "-ffp-contract=off")
_INT32_MAX = (1 << 31) - 1
_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1


class HipRtcFgmresCheckpointHistoryV1Error(HipRtcError):
    """Stable fixed-module error with launch acceptance disposition."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        compile_log: str = "",
        launch_disposition: str | None = None,
    ) -> None:
        if launch_disposition not in {
            None,
            "not_attempted",
            "rejected",
            "ambiguous",
        }:
            raise ValueError("launch_disposition is invalid")
        self.launch_disposition = launch_disposition
        super().__init__(code, message, compile_log=compile_log)


@dataclass(frozen=True, slots=True)
class HipRtcFgmresCheckpointHistoryKernelIdentityV1:
    schema_version: str
    abi_version: int
    blob_abi_version: int
    kernel_name: str
    initialize_symbol: str
    capture_symbol: str
    block_size: int
    blob_abi_hash: str
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

    @property
    def kernel_symbols(self) -> tuple[str, str]:
        return (self.initialize_symbol, self.capture_symbol)

    def to_dict(self) -> dict[str, Any]:
        validate_hip_rtc_fgmres_checkpoint_history_identity_v1(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class HipRtcFgmresCheckpointHistoryKernelV1:
    """Loaded two-symbol module with explicit same-stream fence tracking."""

    __slots__ = (
        "_runtime",
        "_module",
        "_initialize_function",
        "_capture_function",
        "_identity",
        "_closed",
        "_pending_stream_pointer",
        "_accepted_launch_count",
        "_pending_uncertain",
    )

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        initialize_function: ctypes.c_void_p,
        capture_function: ctypes.c_void_p,
        identity: HipRtcFgmresCheckpointHistoryKernelIdentityV1,
    ) -> None:
        self._runtime = runtime
        self._module = module
        self._initialize_function = initialize_function
        self._capture_function = capture_function
        self._identity = identity
        self._closed = False
        self._pending_stream_pointer: int | None = None
        self._accepted_launch_count = 0
        self._pending_uncertain = False

    @property
    def identity(self) -> HipRtcFgmresCheckpointHistoryKernelIdentityV1:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def accepted_launch_count(self) -> int:
        return self._accepted_launch_count

    @property
    def pending(self) -> bool:
        return self._accepted_launch_count > 0 or self._pending_uncertain

    def launch_initialize(
        self,
        stream: Any,
        free_dof_count: int,
        maximum_restart_count: int,
        solution_history_blob: Any,
        true_residual_history_blob: Any,
    ) -> None:
        f, r = _dimensions(free_dof_count, maximum_restart_count)
        pointers = _pointer_arguments(
            (
                ("solution_history_blob", solution_history_blob),
                ("true_residual_history_blob", true_residual_history_blob),
            )
        )
        if pointers[0] == pointers[1]:
            _fail(
                "hip_rtc_fgmres_checkpoint_history_alias_invalid",
                "History blobs must not alias.",
                disposition="not_attempted",
            )
        self._launch(
            self._initialize_function,
            stream=stream,
            scalar_values=(f, r),
            pointer_values=pointers,
            operation="history initialize",
        )

    def launch_capture(
        self,
        stream: Any,
        expected_restart: int,
        expected_column: int,
        expected_end_iteration: int,
        free_dof_count: int,
        maximum_restart_count: int,
        solution_x: Any,
        true_residual: Any,
        solve_record: Any,
        solution_history_blob: Any,
        true_residual_history_blob: Any,
    ) -> None:
        f, r = _dimensions(free_dof_count, maximum_restart_count)
        restart = _bounded_int(
            expected_restart,
            "expected_restart",
            1,
            r,
        )
        column = _bounded_int(
            expected_column,
            "expected_column",
            0,
            _INT32_MAX,
        )
        end_iteration = _bounded_int(
            expected_end_iteration,
            "expected_end_iteration",
            1,
            _INT32_MAX,
        )
        pointers = _pointer_arguments(
            (
                ("solution_x", solution_x),
                ("true_residual", true_residual),
                ("solve_record", solve_record),
                ("solution_history_blob", solution_history_blob),
                ("true_residual_history_blob", true_residual_history_blob),
            )
        )
        if len(set(pointers)) != len(pointers):
            _fail(
                "hip_rtc_fgmres_checkpoint_history_alias_invalid",
                "Capture sources and destinations must have distinct bases.",
                disposition="not_attempted",
            )
        self._launch(
            self._capture_function,
            stream=stream,
            scalar_values=(restart, column, end_iteration, f, r),
            pointer_values=pointers,
            operation="checkpoint history capture",
        )

    def acknowledge_stream_fence(self, stream: Any) -> int:
        """Clear pending module work after an externally observed same-stream fence."""

        self._require_open()
        stream_pointer = _runtime_pointer(stream, "stream")
        if self._pending_stream_pointer not in {None, stream_pointer}:
            _fail(
                "hip_rtc_fgmres_checkpoint_history_fence_stream_invalid",
                "Fence stream does not match the launch stream.",
                disposition="not_attempted",
            )
        acknowledged = self._accepted_launch_count
        self._accepted_launch_count = 0
        self._pending_uncertain = False
        self._pending_stream_pointer = None
        return acknowledged

    def close(self) -> None:
        if self._closed:
            return
        if self.pending:
            _fail(
                "hip_rtc_fgmres_checkpoint_history_pending_work",
                "The history module cannot unload before a same-stream fence.",
                disposition="not_attempted",
            )
        try:
            status = int(self._runtime.unload(self._module))
        except Exception as exc:
            raise HipRtcFgmresCheckpointHistoryV1Error(
                "hip_rtc_fgmres_checkpoint_history_module_unload_failed",
                f"hipModuleUnload raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            raise HipRtcFgmresCheckpointHistoryV1Error(
                "hip_rtc_fgmres_checkpoint_history_module_unload_failed",
                "hipModuleUnload failed: " + self._runtime.error_string(status),
            )
        self._module = ctypes.c_void_p()
        self._initialize_function = ctypes.c_void_p()
        self._capture_function = ctypes.c_void_p()
        self._closed = True

    def _launch(
        self,
        function: ctypes.c_void_p,
        *,
        stream: Any,
        scalar_values: tuple[int, ...],
        pointer_values: tuple[int, ...],
        operation: str,
    ) -> None:
        self._require_open()
        stream_pointer = _runtime_pointer(stream, "stream")
        if self._pending_stream_pointer not in {None, stream_pointer}:
            _fail(
                "hip_rtc_fgmres_checkpoint_history_stream_changed",
                "All history launches must use one stream until fenced.",
                disposition="not_attempted",
            )
        scalar_storage = [ctypes.c_int(value) for value in scalar_values]
        pointer_storage = [ctypes.c_void_p(value) for value in pointer_values]
        arguments = [*scalar_storage, *pointer_storage]
        parameters = (ctypes.c_void_p * len(arguments))(
            *(
                ctypes.cast(ctypes.byref(argument), ctypes.c_void_p)
                for argument in arguments
            )
        )
        try:
            status = int(
                self._runtime.launch(
                    function,
                    grid_x=1,
                    block_x=HIP_FGMRES_CHECKPOINT_HISTORY_BLOCK_SIZE_V1,
                    stream=ctypes.c_void_p(stream_pointer),
                    parameters=parameters,
                )
            )
        except BaseException as exc:
            self._pending_stream_pointer = stream_pointer
            self._pending_uncertain = True
            if not isinstance(exc, Exception):
                raise
            raise HipRtcFgmresCheckpointHistoryV1Error(
                "hip_rtc_fgmres_checkpoint_history_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
                launch_disposition="ambiguous",
            ) from exc
        if status != 0:
            raise HipRtcFgmresCheckpointHistoryV1Error(
                "hip_rtc_fgmres_checkpoint_history_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel failed: "
                f"{self._runtime.error_string(status)}.",
                launch_disposition="rejected",
            )
        self._pending_stream_pointer = stream_pointer
        self._accepted_launch_count += 1

    def _require_open(self) -> None:
        if self._closed:
            _fail(
                "hip_rtc_fgmres_checkpoint_history_kernel_closed",
                "History kernel is closed.",
                disposition="not_attempted",
            )


def compile_hip_rtc_fgmres_checkpoint_history_kernel_v1(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcFgmresCheckpointHistoryKernelV1:
    """Compile and load the package-owned history companion module."""

    try:
        return _compile_impl(loaded_runtime, architecture, hiprtc_library)
    except HipRtcFgmresCheckpointHistoryV1Error:
        raise
    except HipRtcError as exc:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_unexpected_failure",
            f"Unexpected history HIPRTC failure: {type(exc).__name__}.",
        ) from exc


def _compile_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcFgmresCheckpointHistoryKernelV1:
    checked_architecture = _validate_architecture(architecture)
    runtime_identity = _runtime_library_identity(loaded_runtime)
    source = _fixed_source()
    source_hash = _sha256_bytes(source)
    options = (f"--offload-arch={checked_architecture}", *_FIXED_OPTION_SUFFIX)
    rtc = _load_hiprtc_api(hiprtc_library)
    status, rtc_major, rtc_minor = rtc.version()
    if status != 0 or rtc_major < 0 or rtc_minor < 0:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_runtime_init_failed",
            "hipInit failed: " + _runtime_error_string(loaded_runtime, init_status),
        )
    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(rtc, source, options)
    status, module = runtime.load_module(code_object)
    if status != 0 or not module.value:
        if module.value:
            runtime.unload(module)
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_module_load_failed",
            "hipModuleLoadData failed: " + runtime.error_string(status),
            compile_log=compile_log,
        )
    try:
        status, initialize_function = runtime.get_function(
            module,
            HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1,
        )
        if status != 0 or not initialize_function.value:
            raise HipRtcFgmresCheckpointHistoryV1Error(
                "hip_rtc_fgmres_checkpoint_history_initialize_symbol_missing",
                "The fixed initialize symbol is unavailable: "
                + runtime.error_string(status),
                compile_log=compile_log,
            )
        status, capture_function = runtime.get_function(
            module,
            HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1,
        )
        if status != 0 or not capture_function.value:
            raise HipRtcFgmresCheckpointHistoryV1Error(
                "hip_rtc_fgmres_checkpoint_history_capture_symbol_missing",
                "The fixed capture symbol is unavailable: "
                + runtime.error_string(status),
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
        return HipRtcFgmresCheckpointHistoryKernelV1(
            runtime=runtime,
            module=module,
            initialize_function=initialize_function,
            capture_function=capture_function,
            identity=identity,
        )
    except BaseException:
        runtime.unload(module)
        raise


def _build_identity(
    *,
    architecture: str,
    source_hash: str,
    options: tuple[str, ...],
    rtc_version: tuple[int, int],
    rtc_library: HipRtcLibraryIdentity,
    runtime_library: HipRuntimeLibraryIdentity,
    code_object: bytes,
) -> HipRtcFgmresCheckpointHistoryKernelIdentityV1:
    draft = HipRtcFgmresCheckpointHistoryKernelIdentityV1(
        schema_version=(HIP_RTC_FGMRES_CHECKPOINT_HISTORY_IDENTITY_SCHEMA_VERSION_V1),
        abi_version=HIP_RTC_FGMRES_CHECKPOINT_HISTORY_ABI_VERSION_V1,
        blob_abi_version=HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1,
        kernel_name=HIP_RTC_FGMRES_CHECKPOINT_HISTORY_KERNEL_NAME_V1,
        initialize_symbol=(HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1),
        capture_symbol=HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1,
        block_size=HIP_FGMRES_CHECKPOINT_HISTORY_BLOCK_SIZE_V1,
        blob_abi_hash=canonical_hash(
            hip_fgmres_checkpoint_history_blob_abi_payload_v1()
        ),
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
        identity_hash="sha256:" + "0" * 64,
    )
    identity = replace(
        draft,
        identity_hash=canonical_hash(_identity_payload(draft, include_hash=False)),
    )
    return validate_hip_rtc_fgmres_checkpoint_history_identity_v1(identity)


def validate_hip_rtc_fgmres_checkpoint_history_identity_v1(
    identity: HipRtcFgmresCheckpointHistoryKernelIdentityV1,
) -> HipRtcFgmresCheckpointHistoryKernelIdentityV1:
    if type(identity) is not HipRtcFgmresCheckpointHistoryKernelIdentityV1:
        _fail(
            "hip_rtc_fgmres_checkpoint_history_identity_type_invalid",
            "Identity type is invalid.",
        )
    if (
        identity.schema_version
        != HIP_RTC_FGMRES_CHECKPOINT_HISTORY_IDENTITY_SCHEMA_VERSION_V1
        or identity.abi_version != HIP_RTC_FGMRES_CHECKPOINT_HISTORY_ABI_VERSION_V1
        or identity.blob_abi_version
        != HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1
        or identity.kernel_name != HIP_RTC_FGMRES_CHECKPOINT_HISTORY_KERNEL_NAME_V1
        or identity.initialize_symbol
        != HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1
        or identity.capture_symbol
        != HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1
        or identity.block_size != HIP_FGMRES_CHECKPOINT_HISTORY_BLOCK_SIZE_V1
        or identity.blob_abi_hash
        != canonical_hash(hip_fgmres_checkpoint_history_blob_abi_payload_v1())
        or identity.source_resource != _SOURCE_RESOURCE
        or identity.source_sha256 != _sha256_bytes(_fixed_source())
        or identity.compile_options
        != (f"--offload-arch={identity.architecture}", *_FIXED_OPTION_SUFFIX)
        or identity.code_object_byte_length <= 0
        or identity.hiprtc_version_major < 0
        or identity.hiprtc_version_minor < 0
    ):
        _fail(
            "hip_rtc_fgmres_checkpoint_history_identity_invalid",
            "Fixed history identity fields are invalid.",
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_identity_invalid",
            exc.message,
        ) from exc
    hashes = (
        identity.blob_abi_hash,
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        _fail(
            "hip_rtc_fgmres_checkpoint_history_identity_invalid",
            "Identity hashes are invalid.",
        )
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        _fail(
            "hip_rtc_fgmres_checkpoint_history_identity_hash_invalid",
            "Identity hash is invalid.",
        )
    return identity


def _identity_payload(
    identity: HipRtcFgmresCheckpointHistoryKernelIdentityV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "blob_abi_version": identity.blob_abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": {
            "initialize": identity.initialize_symbol,
            "capture": identity.capture_symbol,
        },
        "block_size": identity.block_size,
        "blob_abi_hash": identity.blob_abi_hash,
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


def _fixed_source() -> bytes:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_source_missing",
            f"Package source is unavailable: {type(exc).__name__}.",
        ) from exc
    symbols = (
        HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1,
        HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1,
    )
    if not source or any(
        source.count(symbol.encode("ascii")) != 1 for symbol in symbols
    ):
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_source_invalid",
            "Package source must contain both fixed symbols exactly once.",
        )
    return source


def _dimensions(free_dof_count: Any, maximum_restart_count: Any) -> tuple[int, int]:
    return (
        _bounded_int(free_dof_count, "free_dof_count", 1, _INT32_MAX),
        _bounded_int(
            maximum_restart_count,
            "maximum_restart_count",
            1,
            HIP_FGMRES_MAX_ITERATIONS,
        ),
    )


def _bounded_int(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        _fail(
            "hip_rtc_fgmres_checkpoint_history_launch_contract_invalid",
            f"{label} must be in [{lower}, {upper}].",
            disposition="not_attempted",
        )
    return value


def _pointer_arguments(values: tuple[tuple[str, Any], ...]) -> tuple[int, ...]:
    return tuple(_runtime_pointer(value, label) for label, value in values)


def _runtime_pointer(value: Any, label: str) -> int:
    try:
        pointer = _pointer_integer(value, label)
    except HipRtcError as exc:
        raise HipRtcFgmresCheckpointHistoryV1Error(
            "hip_rtc_fgmres_checkpoint_history_launch_contract_invalid",
            exc.message,
            launch_disposition="not_attempted",
        ) from exc
    if pointer > _UINTPTR_MAX or ctypes.c_void_p(pointer).value != pointer:
        _fail(
            "hip_rtc_fgmres_checkpoint_history_launch_contract_invalid",
            f"{label} does not fit uintptr.",
            disposition="not_attempted",
        )
    return pointer


def _fail(
    code: str,
    message: str,
    *,
    disposition: str | None = None,
) -> None:
    raise HipRtcFgmresCheckpointHistoryV1Error(
        code,
        message,
        launch_disposition=disposition,
    )


__all__ = [
    "HIP_RTC_FGMRES_CHECKPOINT_HISTORY_ABI_VERSION_V1",
    "HIP_RTC_FGMRES_CHECKPOINT_HISTORY_CAPTURE_SYMBOL_V1",
    "HIP_RTC_FGMRES_CHECKPOINT_HISTORY_IDENTITY_SCHEMA_VERSION_V1",
    "HIP_RTC_FGMRES_CHECKPOINT_HISTORY_INITIALIZE_SYMBOL_V1",
    "HIP_RTC_FGMRES_CHECKPOINT_HISTORY_KERNEL_NAME_V1",
    "HipRtcFgmresCheckpointHistoryKernelIdentityV1",
    "HipRtcFgmresCheckpointHistoryKernelV1",
    "HipRtcFgmresCheckpointHistoryV1Error",
    "compile_hip_rtc_fgmres_checkpoint_history_kernel_v1",
    "validate_hip_rtc_fgmres_checkpoint_history_identity_v1",
]
