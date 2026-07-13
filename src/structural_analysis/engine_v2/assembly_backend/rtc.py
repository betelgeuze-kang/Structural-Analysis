"""Fixed-source HIPRTC owner for linear frame/truss element assembly.

The public compiler accepts only a loaded HIP runtime, one plain ``gfx``
architecture, and an optional HIPRTC library path.  Source text, compiler
options, launch geometry, and both module symbols are package owned.

This module deliberately reuses the private HIPRTC program/compiler and HIP
module ABI adapters from :mod:`structural_analysis.engine_v2.rtc_backend.rtc`.
That coupling is narrow and explicit: the existing canonical-CSR source and
identity remain untouched, while program destruction and native module ABI
semantics stay identical across the two fixed-source HIPRTC lanes.
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

HIP_RTC_LINEAR_ASSEMBLY_IDENTITY_SCHEMA_VERSION = (
    "structural-analysis-hip-rtc-linear-frame-truss-assembly-identity.v1"
)
HIP_RTC_LINEAR_ASSEMBLY_ABI_VERSION = 1
HIP_RTC_LINEAR_ASSEMBLY_KERNEL_NAME = "engine_v2_linear_frame_truss_assembly_v1"
HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL = (
    "engine_v2_linear_frame_truss_element_contributions_v1"
)
HIP_RTC_CSR_GATHER_SYMBOL = "engine_v2_linear_frame_truss_csr_gather_v1"
HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE = 144
HIP_RTC_CSR_GATHER_BLOCK_SIZE = 256

ASSEMBLY_DEVICE_ERROR_NONE = 0
ASSEMBLY_DEVICE_ERROR_INVALID_COUNT_OR_GEOMETRY = 1
ASSEMBLY_DEVICE_ERROR_CONNECTIVITY = 2
ASSEMBLY_DEVICE_ERROR_REFERENCE_BOUNDS = 3
ASSEMBLY_DEVICE_ERROR_ELEMENT_CONTRACT = 4
ASSEMBLY_DEVICE_ERROR_NONFINITE = 5
ASSEMBLY_DEVICE_ERROR_LENGTH = 6
ASSEMBLY_DEVICE_ERROR_REFERENCE_AXIS = 7
ASSEMBLY_DEVICE_ERROR_REVERSE_SEGMENT = 8
ASSEMBLY_DEVICE_ERROR_PROPERTY_CONTRACT = 9

REFERENCE_AXIS_GLOBAL_Y = 1
REFERENCE_AXIS_GLOBAL_Z = 2

_SOURCE_RESOURCE = "kernels/engine_v2_linear_frame_truss_assembly_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17")
_INT32_MAX = (1 << 31) - 1
_MAX_ELEMENT_COUNT = _INT32_MAX // 144
_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1


class HipRtcAssemblyError(HipRtcError):
    """Stable fixed-assembly HIPRTC error.

    It is a distinct exact type while retaining the ``code``, ``message``,
    and bounded ``compile_log`` contract used by the existing HIPRTC lane.
    """


@dataclass(frozen=True, slots=True)
class HipRtcLinearAssemblyKernelIdentity:
    """Handle-free identity for one compiled two-symbol assembly module."""

    schema_version: str
    abi_version: int
    kernel_name: str
    element_contribution_symbol: str
    csr_gather_symbol: str
    element_contribution_block_size: int
    csr_gather_block_size: int
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
        return (
            self.element_contribution_symbol,
            self.csr_gather_symbol,
        )

    def to_dict(self) -> dict[str, Any]:
        _validate_identity(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class HipRtcLinearFrameTrussAssemblyKernel:
    """Loaded two-kernel module with explicit, retryable lifetime ownership."""

    __slots__ = (
        "_runtime",
        "_module",
        "_element_function",
        "_gather_function",
        "_identity",
        "_closed",
    )

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        element_function: ctypes.c_void_p,
        gather_function: ctypes.c_void_p,
        identity: HipRtcLinearAssemblyKernelIdentity,
    ) -> None:
        self._runtime = runtime
        self._module = module
        self._element_function = element_function
        self._gather_function = gather_function
        self._identity = identity
        self._closed = False

    @property
    def identity(self) -> HipRtcLinearAssemblyKernelIdentity:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> HipRtcLinearFrameTrussAssemblyKernel:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def launch_element_contributions(
        self,
        stream: Any,
        element_count: int,
        node_count: int,
        material_count: int,
        section_count: int,
        coordinates: Any,
        connectivity: Any,
        element_type: Any,
        formulation: Any,
        material_index: Any,
        section_index: Any,
        material_law_code: Any,
        materials: Any,
        section_family_code: Any,
        sections: Any,
        rolls: Any,
        reference_axis_code: Any,
        contributions: Any,
        error_flag: Any,
    ) -> None:
        """Launch one 144-thread block for every 12-DOF element.

        ``reference_axis_code`` is a device ``uint8`` array using exactly
        ``1=global Y`` and ``2=global Z``.  The host must select global Z
        except when ``abs(local_x.z) > 0.9``, where it must select global Y.
        The device consumes that hash-bound decision and does not rederive
        the threshold comparison.
        """

        self._require_open()
        checked_element_count = _signed_int32(element_count, "element_count")
        if checked_element_count > _MAX_ELEMENT_COUNT:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_launch_contract_invalid",
                "element_count must keep C=144E within signed int32 capacity.",
            )
        counts = (
            checked_element_count,
            _signed_int32(node_count, "node_count"),
            _signed_int32(material_count, "material_count"),
            _signed_int32(section_count, "section_count"),
        )
        pointers = _pointer_arguments(
            (
                ("coordinates", coordinates),
                ("connectivity", connectivity),
                ("element_type", element_type),
                ("formulation", formulation),
                ("material_index", material_index),
                ("section_index", section_index),
                ("material_law_code", material_law_code),
                ("materials", materials),
                ("section_family_code", section_family_code),
                ("sections", sections),
                ("rolls", rolls),
                ("reference_axis_code", reference_axis_code),
                ("contributions", contributions),
                ("error_flag", error_flag),
            )
        )
        self._launch(
            self._element_function,
            stream=stream,
            grid_x=counts[0],
            block_x=HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE,
            scalar_values=counts,
            pointer_values=pointers,
            operation="element contribution",
        )

    def launch_csr_gather(
        self,
        stream: Any,
        nnz_count: int,
        contribution_count: int,
        contributions: Any,
        reverse_segment_offsets: Any,
        reverse_contribution_indices: Any,
        csr_values: Any,
        error_flag: Any,
    ) -> None:
        """Gather stable reverse segments into sorted CSR value slots."""

        self._require_open()
        counts = (
            _signed_int32(nnz_count, "nnz_count"),
            _signed_int32(contribution_count, "contribution_count"),
        )
        pointers = _pointer_arguments(
            (
                ("contributions", contributions),
                ("reverse_segment_offsets", reverse_segment_offsets),
                (
                    "reverse_contribution_indices",
                    reverse_contribution_indices,
                ),
                ("csr_values", csr_values),
                ("error_flag", error_flag),
            )
        )
        grid_x = (
            counts[0] + HIP_RTC_CSR_GATHER_BLOCK_SIZE - 1
        ) // HIP_RTC_CSR_GATHER_BLOCK_SIZE
        self._launch(
            self._gather_function,
            stream=stream,
            grid_x=grid_x,
            block_x=HIP_RTC_CSR_GATHER_BLOCK_SIZE,
            scalar_values=counts,
            pointer_values=pointers,
            operation="CSR gather",
        )

    def close(self) -> None:
        """Unload once; failed unload preserves ownership for a later retry."""

        if self._closed:
            return
        try:
            status = int(self._runtime.unload(self._module))
        except Exception as exc:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_module_unload_failed",
                f"hipModuleUnload raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_module_unload_failed",
                f"hipModuleUnload failed: {self._runtime.error_string(status)}.",
            )
        self._module = ctypes.c_void_p()
        self._element_function = ctypes.c_void_p()
        self._gather_function = ctypes.c_void_p()
        self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_kernel_closed",
                "HIPRTC assembly kernel is closed.",
            )

    def _launch(
        self,
        function: ctypes.c_void_p,
        *,
        stream: Any,
        grid_x: int,
        block_x: int,
        scalar_values: tuple[int, ...],
        pointer_values: tuple[int, ...],
        operation: str,
    ) -> None:
        stream_storage = ctypes.c_void_p(_runtime_pointer(stream, "stream"))
        scalar_storage = [ctypes.c_int(value) for value in scalar_values]
        pointer_storage = [ctypes.c_void_p(value) for value in pointer_values]
        argument_storage = [*scalar_storage, *pointer_storage]
        parameters = (ctypes.c_void_p * len(argument_storage))(
            *(
                ctypes.cast(ctypes.byref(argument), ctypes.c_void_p)
                for argument in argument_storage
            )
        )
        try:
            status = int(
                self._runtime.launch(
                    function,
                    grid_x=grid_x,
                    block_x=block_x,
                    stream=stream_storage,
                    parameters=parameters,
                )
            )
        except HipRtcAssemblyError:
            raise
        except Exception as exc:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel failed: "
                f"{self._runtime.error_string(status)}.",
            )


def compile_hip_rtc_linear_frame_truss_assembly_kernel(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcLinearFrameTrussAssemblyKernel:
    """Compile and load the package-owned two-symbol assembly module."""

    try:
        return _compile_assembly_kernel_impl(
            loaded_runtime,
            architecture,
            hiprtc_library,
        )
    except HipRtcAssemblyError:
        raise
    except HipRtcError as exc:
        raise HipRtcAssemblyError(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_unexpected_failure",
            f"Unexpected HIPRTC assembly pipeline failure: {type(exc).__name__}.",
        ) from exc


def _compile_assembly_kernel_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcLinearFrameTrussAssemblyKernel:
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
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_runtime_init_failed",
            f"hipInit failed: {_runtime_error_string(loaded_runtime, init_status)}.",
        )

    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(rtc, source, options)
    status, module = runtime.load_module(code_object)
    if status != 0 or not module.value:
        if module.value:
            try:
                cleanup_status = int(runtime.unload(module))
            except Exception as cleanup_exc:
                raise HipRtcAssemblyError(
                    "hip_rtc_assembly_module_cleanup_failed",
                    "hipModuleLoadData failed and cleanup raised "
                    f"{type(cleanup_exc).__name__}.",
                    compile_log=compile_log,
                ) from cleanup_exc
            if cleanup_status != 0:
                raise HipRtcAssemblyError(
                    "hip_rtc_assembly_module_cleanup_failed",
                    "hipModuleLoadData failed and cleanup failed: "
                    f"{runtime.error_string(cleanup_status)}.",
                    compile_log=compile_log,
                )
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_module_load_failed",
            f"hipModuleLoadData failed: {runtime.error_string(status)}.",
            compile_log=compile_log,
        )
    try:
        status, element_function = runtime.get_function(
            module,
            HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL,
        )
        if status != 0 or not element_function.value:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_element_symbol_missing",
                "hipModuleGetFunction failed for the fixed element "
                f"contribution symbol: {runtime.error_string(status)}.",
                compile_log=compile_log,
            )
        status, gather_function = runtime.get_function(
            module,
            HIP_RTC_CSR_GATHER_SYMBOL,
        )
        if status != 0 or not gather_function.value:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_gather_symbol_missing",
                "hipModuleGetFunction failed for the fixed CSR gather "
                f"symbol: {runtime.error_string(status)}.",
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
        return HipRtcLinearFrameTrussAssemblyKernel(
            runtime=runtime,
            module=module,
            element_function=element_function,
            gather_function=gather_function,
            identity=identity,
        )
    except Exception as primary:
        try:
            cleanup_status = int(runtime.unload(module))
        except Exception as cleanup_exc:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_module_cleanup_failed",
                f"{primary}; hipModuleUnload cleanup raised "
                f"{type(cleanup_exc).__name__}.",
                compile_log=(
                    primary.compile_log
                    if isinstance(primary, HipRtcError)
                    else compile_log
                ),
            ) from primary
        if cleanup_status != 0:
            raise HipRtcAssemblyError(
                "hip_rtc_assembly_module_cleanup_failed",
                f"{primary}; hipModuleUnload cleanup failed: "
                f"{runtime.error_string(cleanup_status)}.",
                compile_log=(
                    primary.compile_log
                    if isinstance(primary, HipRtcError)
                    else compile_log
                ),
            ) from primary
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
) -> HipRtcLinearAssemblyKernelIdentity:
    initial = HipRtcLinearAssemblyKernelIdentity(
        schema_version=HIP_RTC_LINEAR_ASSEMBLY_IDENTITY_SCHEMA_VERSION,
        abi_version=HIP_RTC_LINEAR_ASSEMBLY_ABI_VERSION,
        kernel_name=HIP_RTC_LINEAR_ASSEMBLY_KERNEL_NAME,
        element_contribution_symbol=HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL,
        csr_gather_symbol=HIP_RTC_CSR_GATHER_SYMBOL,
        element_contribution_block_size=(HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE),
        csr_gather_block_size=HIP_RTC_CSR_GATHER_BLOCK_SIZE,
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
    identity: HipRtcLinearAssemblyKernelIdentity,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": {
            "element_contribution": identity.element_contribution_symbol,
            "csr_gather": identity.csr_gather_symbol,
        },
        "launch_geometry": {
            "element_contribution_block_size": (
                identity.element_contribution_block_size
            ),
            "csr_gather_block_size": identity.csr_gather_block_size,
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


def _validate_identity(identity: Any) -> None:
    if type(identity) is not HipRtcLinearAssemblyKernelIdentity:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            "Assembly kernel identity type is invalid.",
        )
    integer_fields = (
        identity.abi_version,
        identity.element_contribution_block_size,
        identity.csr_gather_block_size,
        identity.hiprtc_version_major,
        identity.hiprtc_version_minor,
        identity.code_object_byte_length,
    )
    string_fields = (
        identity.schema_version,
        identity.kernel_name,
        identity.element_contribution_symbol,
        identity.csr_gather_symbol,
        identity.source_resource,
        identity.source_sha256,
        identity.architecture,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if (
        any(type(value) is not int for value in integer_fields)
        or any(type(value) is not str for value in string_fields)
        or type(identity.compile_options) is not tuple
        or any(type(value) is not str for value in identity.compile_options)
    ):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            "Assembly identity fields require exact scalar and tuple types.",
        )
    if (
        identity.schema_version != HIP_RTC_LINEAR_ASSEMBLY_IDENTITY_SCHEMA_VERSION
        or identity.abi_version != HIP_RTC_LINEAR_ASSEMBLY_ABI_VERSION
        or identity.kernel_name != HIP_RTC_LINEAR_ASSEMBLY_KERNEL_NAME
        or identity.element_contribution_symbol != HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL
        or identity.csr_gather_symbol != HIP_RTC_CSR_GATHER_SYMBOL
        or identity.element_contribution_block_size
        != HIP_RTC_ELEMENT_CONTRIBUTION_BLOCK_SIZE
        or identity.csr_gather_block_size != HIP_RTC_CSR_GATHER_BLOCK_SIZE
        or identity.source_resource != _SOURCE_RESOURCE
    ):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            "Fixed assembly kernel ABI identity is invalid.",
        )
    if identity.source_sha256 != _sha256_bytes(_fixed_source()):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            "Assembly source hash does not match the package-owned source.",
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            exc.message,
        ) from exc
    expected_options = (
        f"--offload-arch={identity.architecture}",
        *_FIXED_OPTION_SUFFIX,
    )
    if identity.compile_options != expected_options:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            "Assembly kernel compile options are not fixed.",
        )
    hashes = (
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            "Assembly kernel identity has an invalid SHA-256.",
        )
    if (
        identity.hiprtc_version_major < 0
        or identity.hiprtc_version_minor < 0
        or identity.code_object_byte_length <= 0
    ):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_invalid",
            "Assembly kernel version or code-object length is invalid.",
        )
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_identity_hash_mismatch",
            "Assembly kernel identity hash is invalid.",
        )


def _fixed_source() -> bytes:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_source_missing",
            f"The package-owned assembly source is unavailable: {type(exc).__name__}.",
        ) from exc
    symbols = (
        HIP_RTC_ELEMENT_CONTRIBUTION_SYMBOL,
        HIP_RTC_CSR_GATHER_SYMBOL,
    )
    if not source or any(
        source.count(symbol.encode("ascii")) != 1 for symbol in symbols
    ):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_source_invalid",
            "The package-owned assembly source must contain both fixed "
            "symbols exactly once.",
        )
    return source


def _signed_int32(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= _INT32_MAX
    ):
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_launch_contract_invalid",
            f"{label} must be a positive signed int32 value.",
        )
    return value


def _pointer_arguments(
    values: tuple[tuple[str, Any], ...],
) -> tuple[int, ...]:
    return tuple(_runtime_pointer(value, label) for label, value in values)


def _runtime_pointer(value: Any, label: str) -> int:
    try:
        pointer = _pointer_integer(value, label)
    except HipRtcError as exc:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_launch_contract_invalid",
            exc.message,
        ) from exc
    if pointer > _UINTPTR_MAX:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_launch_contract_invalid",
            f"{label} exceeds the native uintptr capacity.",
        )
    packed = ctypes.c_void_p(pointer)
    if packed.value != pointer:
        raise HipRtcAssemblyError(
            "hip_rtc_assembly_launch_contract_invalid",
            f"{label} does not round-trip through ctypes.c_void_p.",
        )
    return pointer
