"""Fail-closed artifact contract for the Engine v2 HIP CSR kernel.

The artifact launches one fused canonical-CSR residual/JVP operation on a
caller-owned stream.  This module does not allocate device memory, transfer
buffers, synchronize a stream, select a device, invoke the CPU backend, or
provide a fallback path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import ctypes
from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Literal

from jsonschema import Draft202012Validator

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

HIP_CSR_KERNEL_ARTIFACT_SCHEMA_VERSION = (
    "structural-analysis-hip-csr-kernel-artifact.v1"
)
HIP_CSR_KERNEL_ARTIFACT_VERSION = (
    "engine-v2-canonical-csr-residual-jvp.v1"
)
HIP_CSR_KERNEL_ABI_VERSION = 1
HIP_CSR_KERNEL_BLOCK_SIZE = 256
HIP_CSR_KERNEL_ENTRYPOINT = "engine_v2_hip_csr_launch"
HIP_CSR_KERNEL_LAST_ERROR_ENTRYPOINT = "engine_v2_hip_csr_last_error"
HIP_CSR_KERNEL_REQUIRED_FLAGS = (
    "-O3",
    "-std=c++17",
    "-fPIC",
    "-shared",
    "-fno-fast-math",
    "-ffp-contract=off",
)
HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES = (
    "CUDA_PATH",
    "DEVICE_LIB_PATH",
    "HCC_AMDGPU_TARGET",
    "HCC_EXTRA_LIBRARIES",
    "HIPCC",
    "HIPCC_COMPILE_FLAGS_APPEND",
    "HIPCC_COMPILER",
    "HIPCC_LINKER",
    "HIPCC_LINK_FLAGS_APPEND",
    "HIPCXX",
    "HIP_CLANG_HCC_COMPAT_MODE",
    "HIP_CLANG_LAUNCHER",
    "HIP_CLANG_PATH",
    "HIP_COMPILE_CXX_AS_HIP",
    "HIP_COMPILER",
    "HIP_DEVICE_LIB_PATH",
    "HIP_LIB_PATH",
    "HIP_PATH",
    "HIP_PLATFORM",
    "HIP_ROCCLR_HOME",
    "HIP_RUNTIME",
    "HIP_USE_PERL_SCRIPTS",
    "ROCM_HOME",
    "ROCM_LLVM_PATH",
    "ROCM_PATH",
    "ROCM_ROOT",
)

_DTYPE_I32_LE = 1
_DTYPE_F64_LE = 2
_MAX_LAST_ERROR_BYTES = 256
_TARGET_PATTERN = re.compile(r"^gfx[0-9a-f]{3,8}(?::[a-z0-9_+\-]+)?$")
_HIP_VERSION_PATTERN = re.compile(
    r"(?:HIP\s+version|HIP_VERSION)\s*[:=]\s*([0-9]+\.[0-9]+)",
    re.IGNORECASE,
)
_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUIRED_DEVICE_LIBRARY_NAMES = frozenset({"ocml.bc", "ockl.bc"})
_LOADED_KERNEL_PROVENANCE = object()

HIP_CSR_KERNEL_STABLE_ERROR_CODES = frozenset(
    {
        "hip_csr_source_unavailable",
        "hip_csr_source_hash_failed",
        "hip_csr_target_invalid",
        "hip_csr_hipcc_unavailable",
        "hip_csr_compiler_identity_failed",
        "hip_csr_compiler_identity_invalid",
        "hip_csr_toolchain_environment_override",
        "hip_csr_device_libraries_unavailable",
        "hip_csr_device_libraries_mismatch",
        "hip_csr_device_libraries_hash_failed",
        "hip_csr_compile_failed",
        "hip_csr_artifact_not_produced",
        "hip_csr_prebuilt_artifact_unavailable",
        "hip_csr_artifact_hash_invalid",
        "hip_csr_artifact_hash_failed",
        "hip_csr_artifact_hash_mismatch",
        "hip_csr_artifact_load_failed",
        "hip_csr_artifact_symbol_missing",
        "hip_csr_artifact_abi_mismatch",
        "hip_csr_artifact_target_mismatch",
        "hip_csr_artifact_descriptor_mismatch",
        "hip_csr_artifact_receipt_type_invalid",
        "hip_csr_artifact_receipt_schema_invalid",
        "hip_csr_artifact_receipt_semantics_invalid",
        "hip_csr_artifact_receipt_hash_mismatch",
        "hip_csr_launch_argument_invalid",
        "hip_csr_kernel_launch_failed",
    }
)


class HipCsrKernelArtifactError(RuntimeError):
    """Stable fail-closed error with a bounded message and JSON path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        if code not in HIP_CSR_KERNEL_STABLE_ERROR_CODES:
            raise ValueError(f"Unknown HIP CSR artifact error code: {code}")
        self.code = code
        self.path = path
        self.message = _bounded_message(message)
        super().__init__(f"{code}@{path}: {self.message}")


class _BufferViewV1(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
        ("pointer", ctypes.c_void_p),
        ("byte_length", ctypes.c_uint64),
        ("dtype", ctypes.c_uint32),
        ("rank", ctypes.c_uint32),
        ("shape", ctypes.c_int64 * 2),
        ("strides", ctypes.c_int64 * 2),
    ]


class _CanonicalCsrV1(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
        ("dof_count", ctypes.c_int32),
        ("nnz_count", ctypes.c_int32),
        ("row_ptr", _BufferViewV1),
        ("column_indices", _BufferViewV1),
        ("values", _BufferViewV1),
    ]


class _ResidualJvpRequestV1(ctypes.Structure):
    _fields_ = [
        ("abi_version", ctypes.c_uint32),
        ("struct_size", ctypes.c_uint32),
        ("csr", _CanonicalCsrV1),
        ("load", _BufferViewV1),
        ("state", _BufferViewV1),
        ("direction", _BufferViewV1),
        ("residual_out", _BufferViewV1),
        ("jvp_out", _BufferViewV1),
        ("stream", ctypes.c_void_p),
    ]


@dataclass(frozen=True, slots=True)
class HipCsrDescriptorLayout:
    buffer_view_size: int
    canonical_csr_size: int
    residual_jvp_request_size: int
    dtype_i32_le: int = _DTYPE_I32_LE
    dtype_f64_le: int = _DTYPE_F64_LE

    def to_dict(self) -> dict[str, int]:
        return {
            "buffer_view_size": self.buffer_view_size,
            "canonical_csr_size": self.canonical_csr_size,
            "residual_jvp_request_size": self.residual_jvp_request_size,
            "dtype_i32_le": self.dtype_i32_le,
            "dtype_f64_le": self.dtype_f64_le,
        }


@dataclass(frozen=True, slots=True)
class HipCsrCompilerIdentity:
    path: str
    root: str
    identity: str
    identity_hash: str
    hip_version: str
    ambient_override_policy: Literal["reject_if_present"]
    rejected_environment_override_names: tuple[str, ...]
    ambient_overrides_absent: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "root": self.root,
            "identity": self.identity,
            "identity_hash": self.identity_hash,
            "hip_version": self.hip_version,
            "ambient_override_policy": self.ambient_override_policy,
            "rejected_environment_override_names": list(
                self.rejected_environment_override_names
            ),
            "ambient_overrides_absent": self.ambient_overrides_absent,
        }


@dataclass(frozen=True, slots=True)
class HipCsrDeviceLibrariesIdentity:
    path: str
    content_hash: str
    bitcode_file_count: int
    matching_compiler_root_asserted: Literal[True]
    matching_hip_version_asserted: Literal[True]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "content_hash": self.content_hash,
            "bitcode_file_count": self.bitcode_file_count,
            "matching_compiler_root_asserted": (
                self.matching_compiler_root_asserted
            ),
            "matching_hip_version_asserted": (
                self.matching_hip_version_asserted
            ),
        }


@dataclass(frozen=True, slots=True)
class HipCsrKernelToolchain:
    compiler: HipCsrCompilerIdentity
    device_libraries: HipCsrDeviceLibrariesIdentity


@dataclass(frozen=True, slots=True)
class HipCsrKernelArtifactReceipt:
    schema_version: str
    artifact_version: str
    status: Literal["artifact_ready"]
    status_code: Literal["hip_csr_kernel_artifact_ready"]
    backend: Literal["hip_native"]
    entrypoint: str
    last_error_entrypoint: str
    abi_version: int
    block_size: int
    descriptor_layout: HipCsrDescriptorLayout
    source_path: str
    library_path: str
    source_hash: str
    library_hash: str
    artifact_hash: str
    abi_hash: str
    build_target_hash: str
    compiler: HipCsrCompilerIdentity
    device_libraries: HipCsrDeviceLibrariesIdentity
    targets: tuple[str, ...]
    flags: tuple[str, ...]
    fallback_policy: Literal["forbidden"]
    fallback_used: Literal[False]
    operator_execution_proven: Literal[False]
    numerical_parity_proven: Literal[False]
    speedup_proven: Literal[False]
    receipt_hash: str

    def to_dict(self) -> dict[str, Any]:
        validate_hip_csr_kernel_artifact_receipt(self)
        return _artifact_payload(self, include_receipt_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class _NativeArtifactFacts:
    cdll: Any
    abi_version: int
    block_size: int
    targets: tuple[str, ...]
    descriptor_layout: HipCsrDescriptorLayout
    launch: Any
    last_error: Any


class LoadedHipCsrKernel:
    """Process-local kernel artifact bound with ``ctypes.RTLD_LOCAL``."""

    __slots__ = (
        "_cdll",
        "_launch",
        "_last_error",
        "_loader_provenance",
        "artifact_receipt",
    )

    def __init__(
        self,
        facts: _NativeArtifactFacts,
        artifact_receipt: HipCsrKernelArtifactReceipt,
        *,
        _provenance: object,
    ) -> None:
        if _provenance is not _LOADED_KERNEL_PROVENANCE:
            raise TypeError(
                "LoadedHipCsrKernel must be created by the verified artifact loader."
            )
        self._cdll = facts.cdll
        self._launch = facts.launch
        self._last_error = facts.last_error
        self._loader_provenance = _provenance
        self.artifact_receipt = artifact_receipt

    def launch_residual_jvp(
        self,
        *,
        row_count: int,
        nnz_count: int,
        row_ptr: Any,
        column_indices: Any,
        values: Any,
        load: Any,
        state: Any,
        direction: Any,
        residual_out: Any,
        jvp_out: Any,
        stream: Any,
    ) -> None:
        """Enqueue one fused operation without copying or synchronizing."""

        rows = _positive_i32(row_count, "row_count")
        nnz = _positive_i32(nnz_count, "nnz_count")
        csr = _CanonicalCsrV1(
            abi_version=HIP_CSR_KERNEL_ABI_VERSION,
            struct_size=ctypes.sizeof(_CanonicalCsrV1),
            dof_count=rows,
            nnz_count=nnz,
            row_ptr=_view(row_ptr, rows + 1, _DTYPE_I32_LE, 4, "row_ptr"),
            column_indices=_view(
                column_indices,
                nnz,
                _DTYPE_I32_LE,
                4,
                "column_indices",
            ),
            values=_view(values, nnz, _DTYPE_F64_LE, 8, "values"),
        )
        request = _ResidualJvpRequestV1(
            abi_version=HIP_CSR_KERNEL_ABI_VERSION,
            struct_size=ctypes.sizeof(_ResidualJvpRequestV1),
            csr=csr,
            load=_view(load, rows, _DTYPE_F64_LE, 8, "load"),
            state=_view(state, rows, _DTYPE_F64_LE, 8, "state"),
            direction=_view(
                direction, rows, _DTYPE_F64_LE, 8, "direction"
            ),
            residual_out=_view(
                residual_out, rows, _DTYPE_F64_LE, 8, "residual_out"
            ),
            jvp_out=_view(jvp_out, rows, _DTYPE_F64_LE, 8, "jvp_out"),
            stream=_pointer_value(stream, "stream"),
        )
        status = int(self._launch(ctypes.byref(request)))
        if status != 0:
            message_buffer = ctypes.create_string_buffer(_MAX_LAST_ERROR_BYTES)
            try:
                self._last_error(
                    ctypes.cast(message_buffer, ctypes.c_void_p),
                    _MAX_LAST_ERROR_BYTES,
                )
                native_message = message_buffer.value.decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                native_message = "native last-error unavailable"
            raise HipCsrKernelArtifactError(
                "hip_csr_kernel_launch_failed",
                "/entrypoint",
                f"Native launch returned {status}: {native_message}",
            )


def probe_hip_csr_kernel_toolchain(
    *,
    hipcc_path: str | Path | None = None,
    device_libraries_path: str | Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> HipCsrKernelToolchain:
    """Prove a same-root HIP compiler/device-library pair or fail closed."""

    _reject_ambient_toolchain_overrides()
    hipcc = _resolve_hipcc(hipcc_path)
    _reject_ambient_toolchain_overrides()
    try:
        completed = runner(
            [str(hipcc), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_compiler_identity_failed",
            "/compiler",
            f"hipcc --version failed: {type(exc).__name__}",
        ) from exc
    if int(getattr(completed, "returncode", 1)) != 0:
        raise HipCsrKernelArtifactError(
            "hip_csr_compiler_identity_failed",
            "/compiler",
            _process_failure("hipcc --version", completed),
        )
    identity = "\n".join(
        part.strip()
        for part in (
            str(getattr(completed, "stdout", "")),
            str(getattr(completed, "stderr", "")),
        )
        if part.strip()
    )
    if not identity:
        raise HipCsrKernelArtifactError(
            "hip_csr_compiler_identity_invalid",
            "/compiler/identity",
            "hipcc returned an empty compiler identity.",
        )
    if len(identity) > 4096:
        raise HipCsrKernelArtifactError(
            "hip_csr_compiler_identity_invalid",
            "/compiler/identity",
            "Compiler identity exceeds the receipt limit of 4096 characters.",
        )
    version_match = _HIP_VERSION_PATTERN.search(identity)
    if version_match is None:
        raise HipCsrKernelArtifactError(
            "hip_csr_compiler_identity_invalid",
            "/compiler/hip_version",
            "Compiler identity does not expose a HIP major.minor version.",
        )
    hip_version = version_match.group(1)
    if len(hip_version) > 32:
        raise HipCsrKernelArtifactError(
            "hip_csr_compiler_identity_invalid",
            "/compiler/hip_version",
            "Compiler HIP version exceeds the receipt limit of 32 characters.",
        )
    compiler_root = hipcc.parent.parent.resolve(strict=True)
    device_libraries = _resolve_device_libraries(
        compiler_root, device_libraries_path
    )
    content_hash, file_count = _device_library_content_hash(device_libraries)
    compiler = HipCsrCompilerIdentity(
        path=str(hipcc),
        root=str(compiler_root),
        identity=identity,
        identity_hash=_sha256_bytes(identity.encode("utf-8")),
        hip_version=hip_version,
        ambient_override_policy="reject_if_present",
        rejected_environment_override_names=(
            HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES
        ),
        ambient_overrides_absent=True,
    )
    libraries = HipCsrDeviceLibrariesIdentity(
        path=str(device_libraries),
        content_hash=content_hash,
        bitcode_file_count=file_count,
        matching_compiler_root_asserted=True,
        matching_hip_version_asserted=True,
    )
    return HipCsrKernelToolchain(compiler, libraries)


def build_hip_csr_kernel_artifact(
    output_path: str | Path,
    *,
    targets: Sequence[str],
    source_path: str | Path | None = None,
    hipcc_path: str | Path | None = None,
    device_libraries_path: str | Path | None = None,
    runner: Callable[..., Any] = subprocess.run,
    cdll_loader: Callable[..., Any] = ctypes.CDLL,
) -> HipCsrKernelArtifactReceipt:
    """Build and attest one explicit-target shared artifact."""

    _reject_ambient_toolchain_overrides()
    canonical_targets = _canonical_targets(targets)
    source = _resolve_source(source_path)
    toolchain = probe_hip_csr_kernel_toolchain(
        hipcc_path=hipcc_path,
        device_libraries_path=device_libraries_path,
        runner=runner,
    )
    try:
        source_hash = _sha256_file(source)
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_source_hash_failed",
            "/source_path",
            f"Could not hash kernel source: {type(exc).__name__}",
        ) from exc

    flags = _build_flags(canonical_targets, toolchain.device_libraries.path)
    output = Path(output_path).expanduser()
    try:
        output_parent = output.parent.resolve(strict=True)
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_not_produced",
            "/library_path",
            "Artifact output parent does not exist.",
        ) from exc
    final_output = output_parent / output.name

    temporary_name: str | None = None
    try:
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{output.name}.",
                suffix=".building",
                dir=output_parent,
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
            Path(temporary_name).unlink()
        except OSError as exc:
            raise HipCsrKernelArtifactError(
                "hip_csr_artifact_not_produced",
                "/library_path",
                f"Could not prepare artifact output: {type(exc).__name__}",
            ) from exc
        command = [
            toolchain.compiler.path,
            str(source),
            "-o",
            temporary_name,
            *flags,
        ]
        _reject_ambient_toolchain_overrides()
        try:
            completed = runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except Exception as exc:
            raise HipCsrKernelArtifactError(
                "hip_csr_compile_failed",
                "/flags",
                f"hipcc invocation failed: {type(exc).__name__}",
            ) from exc
        if int(getattr(completed, "returncode", 1)) != 0:
            raise HipCsrKernelArtifactError(
                "hip_csr_compile_failed",
                "/flags",
                _process_failure("hipcc build", completed),
            )
        temporary_path = Path(temporary_name)
        try:
            produced = (
                temporary_path.is_file()
                and temporary_path.stat().st_size > 0
            )
        except OSError as exc:
            raise HipCsrKernelArtifactError(
                "hip_csr_artifact_not_produced",
                "/library_path",
                f"Could not inspect compiler output: {type(exc).__name__}",
            ) from exc
        if not produced:
            raise HipCsrKernelArtifactError(
                "hip_csr_artifact_not_produced",
                "/library_path",
                "hipcc reported success without a non-empty shared artifact.",
            )
        try:
            library_hash = _sha256_file(temporary_path)
        except OSError as exc:
            raise HipCsrKernelArtifactError(
                "hip_csr_artifact_hash_failed",
                "/library_hash",
                f"Could not hash compiler output: {type(exc).__name__}",
            ) from exc
        native = _inspect_native_artifact(temporary_path, cdll_loader)
        _validate_native_contract(native, canonical_targets)
        receipt = _build_hip_csr_kernel_artifact_receipt(
            source=source,
            final_output=final_output,
            source_hash=source_hash,
            library_hash=library_hash,
            native=native,
            targets=canonical_targets,
            flags=flags,
            toolchain=toolchain,
        )
        try:
            temporary_path.replace(final_output)
        except OSError as exc:
            raise HipCsrKernelArtifactError(
                "hip_csr_artifact_not_produced",
                "/library_path",
                f"Could not atomically promote artifact: {type(exc).__name__}",
            ) from exc
        temporary_name = None
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
    return receipt


def _build_hip_csr_kernel_artifact_receipt(
    *,
    source: Path,
    final_output: Path,
    source_hash: str,
    library_hash: str,
    native: _NativeArtifactFacts,
    targets: tuple[str, ...],
    flags: tuple[str, ...],
    toolchain: HipCsrKernelToolchain,
) -> HipCsrKernelArtifactReceipt:
    """Build and fully validate the receipt before artifact promotion."""

    receipt = HipCsrKernelArtifactReceipt(
        schema_version=HIP_CSR_KERNEL_ARTIFACT_SCHEMA_VERSION,
        artifact_version=HIP_CSR_KERNEL_ARTIFACT_VERSION,
        status="artifact_ready",
        status_code="hip_csr_kernel_artifact_ready",
        backend="hip_native",
        entrypoint=HIP_CSR_KERNEL_ENTRYPOINT,
        last_error_entrypoint=HIP_CSR_KERNEL_LAST_ERROR_ENTRYPOINT,
        abi_version=HIP_CSR_KERNEL_ABI_VERSION,
        block_size=HIP_CSR_KERNEL_BLOCK_SIZE,
        descriptor_layout=native.descriptor_layout,
        source_path=str(source),
        library_path=str(final_output),
        source_hash=source_hash,
        library_hash=library_hash,
        artifact_hash=library_hash,
        abi_hash=_abi_hash(native.descriptor_layout),
        build_target_hash=_build_target_hash(
            targets, flags, toolchain
        ),
        compiler=toolchain.compiler,
        device_libraries=toolchain.device_libraries,
        targets=targets,
        flags=flags,
        fallback_policy="forbidden",
        fallback_used=False,
        operator_execution_proven=False,
        numerical_parity_proven=False,
        speedup_proven=False,
        receipt_hash="sha256:" + ("0" * 64),
    )
    receipt = replace(
        receipt,
        receipt_hash=canonical_hash(
            _artifact_payload(receipt, include_receipt_hash=False)
        ),
    )
    return validate_hip_csr_kernel_artifact_receipt(receipt)


def load_hip_csr_kernel_artifact(
    library_path: str | Path,
    *,
    expected_sha256: str,
    artifact_receipt: HipCsrKernelArtifactReceipt,
    cdll_loader: Callable[..., Any] = ctypes.CDLL,
) -> LoadedHipCsrKernel:
    """Verify an explicit artifact hash/receipt, then bind it process-locally."""

    receipt = validate_hip_csr_kernel_artifact_receipt(artifact_receipt)
    if not isinstance(expected_sha256, str) or not _HASH_PATTERN.fullmatch(
        expected_sha256
    ):
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_hash_invalid",
            "/expected_sha256",
            "expected_sha256 must be an explicit sha256:<64 lowercase hex> value.",
        )
    path = Path(library_path).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_prebuilt_artifact_unavailable",
            "/library_path",
            "Explicit HIP CSR shared artifact is unavailable.",
        ) from exc
    if not resolved.is_file():
        raise HipCsrKernelArtifactError(
            "hip_csr_prebuilt_artifact_unavailable",
            "/library_path",
            "Explicit HIP CSR shared artifact is not a file.",
        )
    try:
        actual_hash = _sha256_file(resolved)
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_hash_failed",
            "/library_hash",
            f"Could not read or hash shared artifact: {type(exc).__name__}",
        ) from exc
    if expected_sha256 != receipt.library_hash or actual_hash != expected_sha256:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_hash_mismatch",
            "/library_hash",
            "Explicit, receipt, and content SHA-256 values do not all match.",
        )
    if str(resolved) != receipt.library_path:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_receipt_semantics_invalid",
            "/library_path",
            "Resolved artifact path does not match the attested library path.",
        )
    native = _inspect_native_artifact(resolved, cdll_loader)
    _validate_native_contract(native, receipt.targets)
    if native.descriptor_layout != receipt.descriptor_layout:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_descriptor_mismatch",
            "/descriptor_layout",
            "Native descriptor layout differs from the artifact receipt.",
        )
    if _abi_hash(native.descriptor_layout) != receipt.abi_hash:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_abi_mismatch",
            "/abi_hash",
            "Native descriptor ABI hash differs from the receipt.",
        )
    return LoadedHipCsrKernel(
        native,
        receipt,
        _provenance=_LOADED_KERNEL_PROVENANCE,
    )


def _is_loader_owned_hip_csr_kernel(kernel: Any) -> bool:
    """Return whether ``kernel`` is the exact sealed loader product type."""

    return (
        type(kernel) is LoadedHipCsrKernel
        and kernel._loader_provenance is _LOADED_KERNEL_PROVENANCE
    )


def parse_hip_csr_kernel_artifact_receipt(
    manifest: Mapping[str, Any],
) -> HipCsrKernelArtifactReceipt:
    """Reconstruct a typed receipt from a strict JSON manifest.

    Parsing is offline: recorded compiler, device-library, source, and shared
    artifact paths are not opened or resolved.  No string, number, sequence,
    or nested object is coerced into another JSON type.
    """

    if not isinstance(manifest, Mapping):
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_receipt_type_invalid",
            "/",
            "Artifact receipt manifest must be a mapping.",
        )
    payload = dict(manifest)
    _validate_artifact_manifest_schema(payload)
    descriptor = payload["descriptor_layout"]
    compiler = payload["compiler"]
    device_libraries = payload["device_libraries"]
    receipt = HipCsrKernelArtifactReceipt(
        schema_version=payload["schema_version"],
        artifact_version=payload["artifact_version"],
        status=payload["status"],
        status_code=payload["status_code"],
        backend=payload["backend"],
        entrypoint=payload["entrypoint"],
        last_error_entrypoint=payload["last_error_entrypoint"],
        abi_version=payload["abi_version"],
        block_size=payload["block_size"],
        descriptor_layout=HipCsrDescriptorLayout(
            buffer_view_size=descriptor["buffer_view_size"],
            canonical_csr_size=descriptor["canonical_csr_size"],
            residual_jvp_request_size=descriptor[
                "residual_jvp_request_size"
            ],
            dtype_i32_le=descriptor["dtype_i32_le"],
            dtype_f64_le=descriptor["dtype_f64_le"],
        ),
        source_path=payload["source_path"],
        library_path=payload["library_path"],
        source_hash=payload["source_hash"],
        library_hash=payload["library_hash"],
        artifact_hash=payload["artifact_hash"],
        abi_hash=payload["abi_hash"],
        build_target_hash=payload["build_target_hash"],
        compiler=HipCsrCompilerIdentity(
            path=compiler["path"],
            root=compiler["root"],
            identity=compiler["identity"],
            identity_hash=compiler["identity_hash"],
            hip_version=compiler["hip_version"],
            ambient_override_policy=compiler["ambient_override_policy"],
            rejected_environment_override_names=tuple(
                compiler["rejected_environment_override_names"]
            ),
            ambient_overrides_absent=compiler["ambient_overrides_absent"],
        ),
        device_libraries=HipCsrDeviceLibrariesIdentity(
            path=device_libraries["path"],
            content_hash=device_libraries["content_hash"],
            bitcode_file_count=device_libraries["bitcode_file_count"],
            matching_compiler_root_asserted=device_libraries[
                "matching_compiler_root_asserted"
            ],
            matching_hip_version_asserted=device_libraries[
                "matching_hip_version_asserted"
            ],
        ),
        targets=tuple(payload["targets"]),
        flags=tuple(payload["flags"]),
        fallback_policy=payload["fallback_policy"],
        fallback_used=payload["fallback_used"],
        operator_execution_proven=payload["operator_execution_proven"],
        numerical_parity_proven=payload["numerical_parity_proven"],
        speedup_proven=payload["speedup_proven"],
        receipt_hash=payload["receipt_hash"],
    )
    return validate_hip_csr_kernel_artifact_receipt(receipt)


def validate_hip_csr_kernel_artifact_receipt(
    receipt: HipCsrKernelArtifactReceipt,
) -> HipCsrKernelArtifactReceipt:
    """Validate strict schema, semantic bindings, and canonical receipt hash."""

    if not isinstance(receipt, HipCsrKernelArtifactReceipt):
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_receipt_type_invalid",
            "/",
            "Expected HipCsrKernelArtifactReceipt.",
        )
    for value, expected, path in (
        (receipt.descriptor_layout, HipCsrDescriptorLayout, "/descriptor_layout"),
        (receipt.compiler, HipCsrCompilerIdentity, "/compiler"),
        (
            receipt.device_libraries,
            HipCsrDeviceLibrariesIdentity,
            "/device_libraries",
        ),
    ):
        if not isinstance(value, expected):
            raise HipCsrKernelArtifactError(
                "hip_csr_artifact_receipt_type_invalid",
                path,
                f"Expected {expected.__name__}.",
            )
    payload = _artifact_payload(receipt, include_receipt_hash=True)
    _validate_artifact_manifest_schema(payload)

    expected_layout = _python_descriptor_layout()
    if receipt.descriptor_layout != expected_layout:
        _receipt_semantic_error(
            "/descriptor_layout", "Descriptor sizes differ from Python ABI v1."
        )
    if receipt.artifact_hash != receipt.library_hash:
        _receipt_semantic_error(
            "/artifact_hash", "artifact_hash must equal library_hash."
        )
    if receipt.abi_hash != _abi_hash(receipt.descriptor_layout):
        _receipt_semantic_error("/abi_hash", "Descriptor ABI hash is stale.")
    expected_targets = _canonical_targets(receipt.targets)
    if receipt.targets != expected_targets:
        _receipt_semantic_error(
            "/targets", "Targets must be sorted, unique, and canonical."
        )
    expected_flags = _build_flags(
        receipt.targets, receipt.device_libraries.path
    )
    if receipt.flags != expected_flags:
        _receipt_semantic_error(
            "/flags", "Compiler flags differ from the exact v1 build contract."
        )
    toolchain = HipCsrKernelToolchain(
        receipt.compiler, receipt.device_libraries
    )
    if receipt.build_target_hash != _build_target_hash(
        receipt.targets, receipt.flags, toolchain
    ):
        _receipt_semantic_error(
            "/build_target_hash", "Build-target hash is stale."
        )
    compiler_root = Path(receipt.compiler.root)
    compiler_path = Path(receipt.compiler.path)
    libraries_path = Path(receipt.device_libraries.path)
    source_path = Path(receipt.source_path)
    library_path = Path(receipt.library_path)
    if not all(
        row.is_absolute()
        for row in (
            compiler_root,
            compiler_path,
            libraries_path,
            source_path,
            library_path,
        )
    ):
        _receipt_semantic_error(
            "/", "All attested source, artifact, and toolchain paths must be absolute."
        )
    if compiler_path.parent.parent != compiler_root or not _is_within(
        libraries_path, compiler_root
    ):
        _receipt_semantic_error(
            "/device_libraries",
            "Device libraries are not bound to the compiler root.",
        )
    if receipt.compiler.identity_hash != _sha256_bytes(
        receipt.compiler.identity.encode("utf-8")
    ):
        _receipt_semantic_error(
            "/compiler/identity_hash", "Compiler identity hash is stale."
        )
    if (
        receipt.compiler.ambient_override_policy != "reject_if_present"
        or receipt.compiler.rejected_environment_override_names
        != HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES
        or receipt.compiler.ambient_overrides_absent is not True
    ):
        _receipt_semantic_error(
            "/compiler",
            "Compiler ambient-override rejection evidence differs from v1.",
        )
    expected_receipt_hash = canonical_hash(
        _artifact_payload(receipt, include_receipt_hash=False)
    )
    if receipt.receipt_hash != expected_receipt_hash:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_receipt_hash_mismatch",
            "/receipt_hash",
            "Artifact receipt canonical hash is stale.",
        )
    return receipt


def _validate_artifact_manifest_schema(payload: dict[str, Any]) -> None:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_receipt_schema_invalid", path, error.message
        )


def _reject_ambient_toolchain_overrides() -> None:
    present = tuple(
        name
        for name in HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES
        if name in os.environ
    )
    if present:
        raise HipCsrKernelArtifactError(
            "hip_csr_toolchain_environment_override",
            "/compiler/environment",
            "Ambient HIP/ROCm toolchain overrides are forbidden: "
            + ", ".join(present),
        )


def _resolve_hipcc(hipcc_path: str | Path | None) -> Path:
    raw: str | None
    if hipcc_path is not None:
        raw = str(hipcc_path)
    else:
        raw = shutil.which("hipcc")
        if raw is None and Path("/opt/rocm/bin/hipcc").is_file():
            raw = "/opt/rocm/bin/hipcc"
        if raw is None:
            versioned = sorted(
                path
                for path in Path("/opt").glob("rocm-*/bin/hipcc")
                if path.is_file()
            )
            if len(versioned) == 1:
                raw = str(versioned[0])
    if not raw:
        raise HipCsrKernelArtifactError(
            "hip_csr_hipcc_unavailable",
            "/compiler/path",
            "No explicit or PATH hipcc executable is available.",
        )
    try:
        path = Path(raw).expanduser().resolve(strict=True)
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_hipcc_unavailable",
            "/compiler/path",
            "hipcc path does not resolve to a file.",
        ) from exc
    if not path.is_file() or not os.access(path, os.X_OK):
        raise HipCsrKernelArtifactError(
            "hip_csr_hipcc_unavailable",
            "/compiler/path",
            "hipcc is not an executable file.",
        )
    return path


def _resolve_device_libraries(
    compiler_root: Path, explicit: str | Path | None
) -> Path:
    if explicit is None:
        candidates = [
            compiler_root / "amdgcn" / "bitcode",
            compiler_root / "lib" / "llvm" / "amdgcn" / "bitcode",
        ]
        llvm_root = compiler_root / "lib" / "llvm"
        if llvm_root.is_dir():
            candidates.extend(
                sorted(llvm_root.glob("*/amdgcn/bitcode"))
            )
        selected = next((row for row in candidates if row.is_dir()), None)
        if selected is None:
            raise HipCsrKernelArtifactError(
                "hip_csr_device_libraries_unavailable",
                "/device_libraries/path",
                "No device-library directory exists inside the compiler root.",
            )
    else:
        selected = Path(explicit).expanduser()
    try:
        resolved = selected.resolve(strict=True)
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_device_libraries_unavailable",
            "/device_libraries/path",
            "Device-library path is unavailable.",
        ) from exc
    if not resolved.is_dir():
        raise HipCsrKernelArtifactError(
            "hip_csr_device_libraries_unavailable",
            "/device_libraries/path",
            "Device-library path is not a directory.",
        )
    if not _is_within(resolved, compiler_root):
        raise HipCsrKernelArtifactError(
            "hip_csr_device_libraries_mismatch",
            "/device_libraries/path",
            "Device libraries must resolve inside the selected hipcc root.",
        )
    names = {path.name for path in resolved.rglob("*.bc") if path.is_file()}
    missing = sorted(_REQUIRED_DEVICE_LIBRARY_NAMES - names)
    if missing:
        raise HipCsrKernelArtifactError(
            "hip_csr_device_libraries_unavailable",
            "/device_libraries/path",
            "Required same-toolchain bitcode is missing: " + ", ".join(missing),
        )
    return resolved


def _device_library_content_hash(path: Path) -> tuple[str, int]:
    try:
        files = sorted(row for row in path.rglob("*.bc") if row.is_file())
        manifest = [
            {
                "path": row.relative_to(path).as_posix(),
                "sha256": _sha256_file(row),
            }
            for row in files
        ]
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_device_libraries_hash_failed",
            "/device_libraries/content_hash",
            f"Could not hash device libraries: {type(exc).__name__}",
        ) from exc
    if not manifest:
        raise HipCsrKernelArtifactError(
            "hip_csr_device_libraries_unavailable",
            "/device_libraries/path",
            "Device-library directory contains no bitcode files.",
        )
    return canonical_hash(manifest), len(manifest)


def _resolve_source(source_path: str | Path | None) -> Path:
    path = (
        Path(source_path).expanduser()
        if source_path is not None
        else Path(__file__).with_name("kernels")
        / "engine_v2_csr_residual_jvp.hip.cpp"
    )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_source_unavailable",
            "/source_path",
            "HIP CSR kernel source is unavailable.",
        ) from exc
    if not resolved.is_file():
        raise HipCsrKernelArtifactError(
            "hip_csr_source_unavailable",
            "/source_path",
            "HIP CSR kernel source is not a file.",
        )
    return resolved


def _canonical_targets(targets: Sequence[str]) -> tuple[str, ...]:
    if isinstance(targets, (str, bytes)):
        raise HipCsrKernelArtifactError(
            "hip_csr_target_invalid",
            "/targets",
            "targets must be a non-string sequence.",
        )
    try:
        rows = tuple(targets)
    except TypeError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_target_invalid", "/targets", "targets must be iterable."
        ) from exc
    if not rows:
        raise HipCsrKernelArtifactError(
            "hip_csr_target_invalid",
            "/targets",
            "At least one explicit gfx target is required.",
        )
    if len(rows) > 32:
        raise HipCsrKernelArtifactError(
            "hip_csr_target_invalid",
            "/targets",
            "At most 32 explicit gfx targets are permitted.",
        )
    if any(isinstance(row, str) and len(row) > 64 for row in rows):
        raise HipCsrKernelArtifactError(
            "hip_csr_target_invalid",
            "/targets",
            "Every target must be at most 64 characters.",
        )
    if any(not isinstance(row, str) or not _TARGET_PATTERN.fullmatch(row) for row in rows):
        raise HipCsrKernelArtifactError(
            "hip_csr_target_invalid",
            "/targets",
            "Every target must be an explicit canonical gfx architecture.",
        )
    if len(set(rows)) != len(rows):
        raise HipCsrKernelArtifactError(
            "hip_csr_target_invalid", "/targets", "Duplicate targets are forbidden."
        )
    return tuple(sorted(rows))


def _build_flags(
    targets: Sequence[str], device_libraries_path: str
) -> tuple[str, ...]:
    target_rows = tuple(targets)
    return (
        *HIP_CSR_KERNEL_REQUIRED_FLAGS,
        *(f"--offload-arch={target}" for target in target_rows),
        f"--rocm-device-lib-path={device_libraries_path}",
        "-DENGINE_V2_HIP_CSR_TARGETS=\"" + ",".join(target_rows) + "\"",
    )


def _inspect_native_artifact(
    path: Path, cdll_loader: Callable[..., Any]
) -> _NativeArtifactFacts:
    try:
        cdll = cdll_loader(
            str(path), mode=getattr(ctypes, "RTLD_LOCAL", 0)
        )
    except Exception as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_load_failed",
            "/library_path",
            f"Shared artifact could not be loaded: {type(exc).__name__}",
        ) from exc
    abi = _bind(cdll, "engine_v2_hip_csr_abi_version", [], ctypes.c_uint32)
    block = _bind(cdll, "engine_v2_hip_csr_block_size", [], ctypes.c_uint32)
    target_fn = _bind(cdll, "engine_v2_hip_csr_targets", [], ctypes.c_char_p)
    buffer_size = _bind(
        cdll, "engine_v2_hip_csr_buffer_view_size", [], ctypes.c_uint32
    )
    csr_size = _bind(
        cdll, "engine_v2_hip_csr_canonical_csr_size", [], ctypes.c_uint32
    )
    request_size = _bind(
        cdll,
        "engine_v2_hip_csr_residual_jvp_request_size",
        [],
        ctypes.c_uint32,
    )
    launch = _bind(
        cdll,
        HIP_CSR_KERNEL_ENTRYPOINT,
        [ctypes.POINTER(_ResidualJvpRequestV1)],
        ctypes.c_int32,
    )
    last_error = _bind(
        cdll,
        HIP_CSR_KERNEL_LAST_ERROR_ENTRYPOINT,
        [ctypes.c_void_p, ctypes.c_uint32],
        ctypes.c_int32,
    )
    try:
        raw_targets = target_fn()
        if not isinstance(raw_targets, bytes):
            raise TypeError("target entrypoint did not return bytes")
        targets_text = raw_targets.decode("ascii", errors="strict")
        targets = tuple(targets_text.split(","))
        layout = HipCsrDescriptorLayout(
            int(buffer_size()), int(csr_size()), int(request_size())
        )
        return _NativeArtifactFacts(
            cdll=cdll,
            abi_version=int(abi()),
            block_size=int(block()),
            targets=targets,
            descriptor_layout=layout,
            launch=launch,
            last_error=last_error,
        )
    except HipCsrKernelArtifactError:
        raise
    except Exception as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_abi_mismatch",
            "/abi_version",
            f"Artifact metadata query failed: {type(exc).__name__}",
        ) from exc


def _bind(cdll: Any, name: str, argtypes: list[Any], restype: Any) -> Any:
    try:
        function = getattr(cdll, name)
    except AttributeError as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_symbol_missing",
            "/entrypoint",
            f"Required artifact symbol is missing: {name}",
        ) from exc
    try:
        function.argtypes = argtypes
        function.restype = restype
    except Exception as exc:
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_abi_mismatch",
            "/entrypoint",
            f"Could not bind artifact symbol {name}: {type(exc).__name__}",
        ) from exc
    return function


def _validate_native_contract(
    native: _NativeArtifactFacts, targets: Sequence[str]
) -> None:
    if (
        native.abi_version != HIP_CSR_KERNEL_ABI_VERSION
        or native.block_size != HIP_CSR_KERNEL_BLOCK_SIZE
    ):
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_abi_mismatch",
            "/abi_version",
            "Artifact ABI version or fixed block size differs from v1.",
        )
    if native.descriptor_layout != _python_descriptor_layout():
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_descriptor_mismatch",
            "/descriptor_layout",
            "Native and Python descriptor layouts differ.",
        )
    if native.targets != tuple(targets):
        raise HipCsrKernelArtifactError(
            "hip_csr_artifact_target_mismatch",
            "/targets",
            "Native target list differs from the explicit artifact target list.",
        )


def _view(
    pointer: Any,
    count: int,
    dtype: int,
    item_size: int,
    label: str,
) -> _BufferViewV1:
    return _BufferViewV1(
        abi_version=HIP_CSR_KERNEL_ABI_VERSION,
        struct_size=ctypes.sizeof(_BufferViewV1),
        pointer=_pointer_value(pointer, label),
        byte_length=count * item_size,
        dtype=dtype,
        rank=1,
        shape=(ctypes.c_int64 * 2)(count, 0),
        strides=(ctypes.c_int64 * 2)(item_size, 0),
    )


def _pointer_value(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raw = None
    elif isinstance(value, int):
        raw = value
    elif isinstance(value, ctypes.c_void_p):
        raw = value.value
    else:
        raw = getattr(value, "value", None)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise HipCsrKernelArtifactError(
            "hip_csr_launch_argument_invalid",
            f"/{label}",
            f"{label} must be a non-null caller-owned pointer.",
        )
    if raw > (2 ** (ctypes.sizeof(ctypes.c_void_p) * 8) - 1):
        raise HipCsrKernelArtifactError(
            "hip_csr_launch_argument_invalid",
            f"/{label}",
            f"{label} exceeds the process pointer width.",
        )
    return raw


def _positive_i32(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > 2**31 - 2
    ):
        raise HipCsrKernelArtifactError(
            "hip_csr_launch_argument_invalid",
            f"/{label}",
            f"{label} must be in [1, 2^31-2].",
        )
    return value


def _python_descriptor_layout() -> HipCsrDescriptorLayout:
    return HipCsrDescriptorLayout(
        ctypes.sizeof(_BufferViewV1),
        ctypes.sizeof(_CanonicalCsrV1),
        ctypes.sizeof(_ResidualJvpRequestV1),
    )


def _abi_hash(layout: HipCsrDescriptorLayout) -> str:
    return canonical_hash(
        {
            "abi_version": HIP_CSR_KERNEL_ABI_VERSION,
            "entrypoint": HIP_CSR_KERNEL_ENTRYPOINT,
            "last_error_entrypoint": HIP_CSR_KERNEL_LAST_ERROR_ENTRYPOINT,
            "block_size": HIP_CSR_KERNEL_BLOCK_SIZE,
            "descriptor_layout": layout.to_dict(),
            "buffer_view": {
                "fields": [
                    "abi_version:u32",
                    "struct_size:u32",
                    "pointer:void*",
                    "byte_length:u64",
                    "dtype:u32",
                    "rank:u32",
                    "shape:i64[2]",
                    "strides:i64[2]",
                ],
                "rank": 1,
            },
            "canonical_csr": {
                "index_dtype": "<i4",
                "value_dtype": "<f8",
                "stored_order": "canonical_csr",
            },
            "stream_contract": "caller_owned_nonblocking",
        }
    )


def _build_target_hash(
    targets: Sequence[str],
    flags: Sequence[str],
    toolchain: HipCsrKernelToolchain,
) -> str:
    return canonical_hash(
        {
            "targets": list(targets),
            "flags": list(flags),
            "compiler_identity_hash": toolchain.compiler.identity_hash,
            "compiler_hip_version": toolchain.compiler.hip_version,
            "ambient_override_policy": (
                toolchain.compiler.ambient_override_policy
            ),
            "rejected_environment_override_names": list(
                toolchain.compiler.rejected_environment_override_names
            ),
            "ambient_overrides_absent": (
                toolchain.compiler.ambient_overrides_absent
            ),
            "device_libraries_hash": toolchain.device_libraries.content_hash,
            "matching_compiler_root_asserted": (
                toolchain.device_libraries.matching_compiler_root_asserted
            ),
            "matching_hip_version_asserted": (
                toolchain.device_libraries.matching_hip_version_asserted
            ),
        }
    )


def _artifact_payload(
    receipt: HipCsrKernelArtifactReceipt, *, include_receipt_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": receipt.schema_version,
        "artifact_version": receipt.artifact_version,
        "status": receipt.status,
        "status_code": receipt.status_code,
        "backend": receipt.backend,
        "entrypoint": receipt.entrypoint,
        "last_error_entrypoint": receipt.last_error_entrypoint,
        "abi_version": receipt.abi_version,
        "block_size": receipt.block_size,
        "descriptor_layout": receipt.descriptor_layout.to_dict(),
        "source_path": receipt.source_path,
        "library_path": receipt.library_path,
        "source_hash": receipt.source_hash,
        "library_hash": receipt.library_hash,
        "artifact_hash": receipt.artifact_hash,
        "abi_hash": receipt.abi_hash,
        "build_target_hash": receipt.build_target_hash,
        "compiler": receipt.compiler.to_dict(),
        "device_libraries": receipt.device_libraries.to_dict(),
        "targets": list(receipt.targets),
        "flags": list(receipt.flags),
        "fallback_policy": receipt.fallback_policy,
        "fallback_used": receipt.fallback_used,
        "operator_execution_proven": receipt.operator_execution_proven,
        "numerical_parity_proven": receipt.numerical_parity_proven,
        "speedup_proven": receipt.speedup_proven,
    }
    if include_receipt_hash:
        payload["receipt_hash"] = receipt.receipt_hash
    return payload


def _receipt_semantic_error(path: str, message: str) -> None:
    raise HipCsrKernelArtifactError(
        "hip_csr_artifact_receipt_semantics_invalid", path, message
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _process_failure(label: str, completed: Any) -> str:
    stderr = str(getattr(completed, "stderr", "")).strip()
    stdout = str(getattr(completed, "stdout", "")).strip()
    detail = stderr or stdout or "no compiler diagnostic"
    return f"{label} returned {getattr(completed, 'returncode', '?')}: {detail}"


def _bounded_message(message: str) -> str:
    compact = " ".join(str(message).split())
    return (compact or "HIP CSR artifact failure")[:512]


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[3]
        / "schemas"
        / "hip_csr_kernel_artifact_v1.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "HIP_CSR_KERNEL_ABI_VERSION",
    "HIP_CSR_KERNEL_ARTIFACT_SCHEMA_VERSION",
    "HIP_CSR_KERNEL_ARTIFACT_VERSION",
    "HIP_CSR_KERNEL_BLOCK_SIZE",
    "HIP_CSR_KERNEL_ENTRYPOINT",
    "HIP_CSR_KERNEL_FORBIDDEN_ENVIRONMENT_OVERRIDES",
    "HIP_CSR_KERNEL_LAST_ERROR_ENTRYPOINT",
    "HIP_CSR_KERNEL_REQUIRED_FLAGS",
    "HIP_CSR_KERNEL_STABLE_ERROR_CODES",
    "HipCsrCompilerIdentity",
    "HipCsrDescriptorLayout",
    "HipCsrDeviceLibrariesIdentity",
    "HipCsrKernelArtifactError",
    "HipCsrKernelArtifactReceipt",
    "HipCsrKernelToolchain",
    "LoadedHipCsrKernel",
    "build_hip_csr_kernel_artifact",
    "load_hip_csr_kernel_artifact",
    "parse_hip_csr_kernel_artifact_receipt",
    "probe_hip_csr_kernel_toolchain",
    "validate_hip_csr_kernel_artifact_receipt",
]
