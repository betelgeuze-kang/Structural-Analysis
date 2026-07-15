"""Persistent HIP model-buffer context with exact transfer telemetry.

This Phase 0 context uploads ``SolverModelBuffers`` only.  It deliberately has
no operator, state, residual/JVP kernel, or solver entrypoint, and therefore
cannot produce a HIP analysis success receipt.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass, replace
from functools import lru_cache
import json
from pathlib import Path
from typing import Any, NoReturn, Protocol

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.buffers import (
    SolverModelBuffers,
    validate_solver_model_buffers,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)

from .native import LoadedHipRuntime, load_hip_native_runtime, probe_hip_capability
from .transfer_audit_v1 import (
    _BOUND_COPY_AUDIT_SNAPSHOT_MINT_V1,
    _BoundHipCopyAuditStateV1,
)
from .types import HipCapabilityReceipt

HIP_CONTEXT_RECEIPT_SCHEMA_VERSION = "structural-analysis-hip-context-receipt.v1"
HIP_CONTEXT_CAPABILITY_PROFILE = "phase0_hip_model_buffer_context_foundation"

_CONTEXT_REASON_CODES = frozenset(
    {
        "hip_native_library_missing",
        "hip_native_abi_mismatch",
        "hip_runtime_init_failed",
        "hip_no_device",
        "hip_device_ordinal_invalid",
        "hip_device_access_failed",
        "hip_allocation_failed",
        "hip_copy_failed",
        "hip_memory_budget_exceeded",
    }
)
_INJECTED_HIP_CONTEXT_RUNTIME_MINT = object()


class HipContextError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class HipFreeKnownNotFreedError(HipContextError):
    """Exact injected-runtime signal that a free call had no device effect."""


class HipFreeOutcomeUncertainError(HipContextError):
    """Exact injected-runtime signal that a free call may have taken effect."""


@dataclass(frozen=True, slots=True)
class HipContextReason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class HipBufferBinding:
    schema_version: str
    model_ir_content_hash: str
    load_pattern_id: str
    numeric_buffer_hash: str
    entity_mapping_hash: str
    artifact_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "model_ir_content_hash": self.model_ir_content_hash,
            "load_pattern_id": self.load_pattern_id,
            "numeric_buffer_hash": self.numeric_buffer_hash,
            "entity_mapping_hash": self.entity_mapping_hash,
            "artifact_hash": self.artifact_hash,
        }


@dataclass(frozen=True, slots=True)
class HipDeviceContextIdentity:
    ordinal: int
    name: str
    architecture: str | None
    runtime_version_raw: int
    driver_version_raw: int
    total_memory_bytes: int
    free_memory_bytes_before_upload: int
    free_memory_bytes_after_upload: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ordinal": self.ordinal,
            "name": self.name,
            "architecture": self.architecture,
            "runtime_version_raw": self.runtime_version_raw,
            "driver_version_raw": self.driver_version_raw,
            "total_memory_bytes": self.total_memory_bytes,
            "free_memory_bytes_before_upload": self.free_memory_bytes_before_upload,
            "free_memory_bytes_after_upload": self.free_memory_bytes_after_upload,
        }


@dataclass(frozen=True, slots=True)
class HipBufferView:
    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: str
    byte_length: int
    data_hash: str
    content_hash: str
    memory_space: str
    device_ordinal: int
    access: str
    initial_transfer: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "shape": list(self.shape),
            "layout": self.layout,
            "byte_length": self.byte_length,
            "data_hash": self.data_hash,
            "content_hash": self.content_hash,
            "memory_space": self.memory_space,
            "device_ordinal": self.device_ordinal,
            "access": self.access,
            "initial_transfer": self.initial_transfer,
        }


@dataclass(frozen=True, slots=True)
class HipContextTelemetry:
    h2d_bytes: int
    d2h_bytes: int
    h2d_operation_count: int
    d2h_operation_count: int
    blocking_copy_count: int
    explicit_sync_count: int
    allocation_count: int
    deallocation_count: int
    current_device_payload_bytes: int
    peak_device_payload_bytes: int
    kernel_launch_count: int = 0
    fallback_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "h2d_bytes": self.h2d_bytes,
            "d2h_bytes": self.d2h_bytes,
            "h2d_operation_count": self.h2d_operation_count,
            "d2h_operation_count": self.d2h_operation_count,
            "blocking_copy_count": self.blocking_copy_count,
            "explicit_sync_count": self.explicit_sync_count,
            "allocation_count": self.allocation_count,
            "deallocation_count": self.deallocation_count,
            "current_device_payload_bytes": self.current_device_payload_bytes,
            "peak_device_payload_bytes": self.peak_device_payload_bytes,
            "kernel_launch_count": self.kernel_launch_count,
            "fallback_count": self.fallback_count,
        }


@dataclass(frozen=True, slots=True)
class HipContextClaims:
    model_buffers_device_resident: bool
    operator_bound: bool = False
    state_bound: bool = False
    residual_jvp_ready: bool = False
    solver_ready: bool = False
    device_resident_newton_krylov: bool = False
    cpu_hip_parity_proven: bool = False
    commercial_readiness: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "model_buffers_device_resident": self.model_buffers_device_resident,
            "operator_bound": self.operator_bound,
            "state_bound": self.state_bound,
            "residual_jvp_ready": self.residual_jvp_ready,
            "solver_ready": self.solver_ready,
            "device_resident_newton_krylov": self.device_resident_newton_krylov,
            "cpu_hip_parity_proven": self.cpu_hip_parity_proven,
            "commercial_readiness": self.commercial_readiness,
        }


@dataclass(frozen=True, slots=True)
class HipContextReceipt:
    status: str
    context_id: str
    actual_backend: str | None
    reason: HipContextReason | None
    capability_receipt_hash: str
    solver_model_buffers: HipBufferBinding
    device: HipDeviceContextIdentity | None
    buffer_views: tuple[HipBufferView, ...]
    telemetry: HipContextTelemetry
    claims: HipContextClaims
    context_receipt_hash: str

    @property
    def schema_version(self) -> str:
        return HIP_CONTEXT_RECEIPT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        validate_hip_context_receipt(self)
        return _context_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipContextOpenResult:
    context: DeviceExecutionContext | None
    capability_receipt: HipCapabilityReceipt
    receipt: HipContextReceipt

    @property
    def ready(self) -> bool:
        return self.context is not None and self.receipt.status == "context_ready"


class HipContextRuntimeProtocol(Protocol):
    @property
    def device_ordinal(self) -> int | None: ...

    def set_device(self, ordinal: int) -> None: ...

    def mem_info(self) -> tuple[int, int]: ...

    def create_stream(self) -> Any: ...

    def malloc(self, byte_length: int) -> Any: ...

    def copy_h2d_async(self, pointer: Any, array: np.ndarray, stream: Any) -> None: ...

    def copy_d2h_async(self, array: np.ndarray, pointer: Any, stream: Any) -> None: ...

    def copy_d2h(self, array: np.ndarray, pointer: Any) -> None: ...

    def completion_export_copy_binding(self) -> Any: ...

    def synchronize(self, stream: Any) -> None: ...

    def free(self, pointer: Any) -> None: ...

    def destroy_stream(self, stream: Any) -> None: ...


class _BoundBlockingD2HCopy:
    """Immutable callable that never re-reads mutable runtime attributes."""

    __slots__ = ("_copy_audit_v1", "_loaded", "_memcpy")

    def __init__(
        self,
        memcpy: Any,
        loaded_runtime: Any,
        copy_audit_v1: _BoundHipCopyAuditStateV1,
    ) -> None:
        object.__setattr__(self, "_memcpy", memcpy)
        object.__setattr__(self, "_loaded", loaded_runtime)
        object.__setattr__(self, "_copy_audit_v1", copy_audit_v1)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __call__(self, array: np.ndarray, pointer: Any) -> None:
        byte_count = int(array.nbytes)
        ticket = self._copy_audit_v1.begin("d2h_blocking", byte_count)
        try:
            status = self._memcpy(
                ctypes.c_void_p(int(array.ctypes.data)),
                pointer,
                byte_count,
                2,
            )
        except BaseException:
            self._copy_audit_v1.finish(ticket, succeeded=False)
            raise
        self._copy_audit_v1.finish(ticket, succeeded=status == 0)
        if status != 0:
            raise HipContextError(
                "hip_copy_failed",
                f"hipMemcpy(D2H): {self._loaded.hip_error_string(status)}",
            )


class _BoundHipContextRuntime:
    def __init__(
        self,
        loaded_runtime: Any,
        *,
        _injected_runtime_mint: object | None = None,
    ) -> None:
        if type(loaded_runtime) is LoadedHipRuntime:
            self._loader_provenance_witness = (
                loaded_runtime._loader_provenance_witness()
            )
            self._injected_runtime_authority_witness = None
        elif _injected_runtime_mint is _INJECTED_HIP_CONTEXT_RUNTIME_MINT:
            self._loader_provenance_witness = None
            self._injected_runtime_authority_witness = (
                _INJECTED_HIP_CONTEXT_RUNTIME_MINT
            )
        else:
            raise TypeError(
                "_BoundHipContextRuntime requires a loader-issued "
                "LoadedHipRuntime; injected runtimes require the private test mint."
            )
        self._loaded = loaded_runtime
        self._device_ordinal: int | None = None
        self._set_device = loaded_runtime.bind(
            "hipSetDevice", [ctypes.c_int], ctypes.c_int
        )
        self._mem_info = loaded_runtime.bind(
            "hipMemGetInfo",
            [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)],
            ctypes.c_int,
        )
        self._stream_create = loaded_runtime.bind(
            "hipStreamCreateWithFlags",
            [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint],
            ctypes.c_int,
        )
        self._stream_destroy = loaded_runtime.bind(
            "hipStreamDestroy", [ctypes.c_void_p], ctypes.c_int
        )
        self._malloc = loaded_runtime.bind(
            "hipMalloc",
            [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t],
            ctypes.c_int,
        )
        self._free = loaded_runtime.bind("hipFree", [ctypes.c_void_p], ctypes.c_int)
        self._memcpy_async = loaded_runtime.bind(
            "hipMemcpyAsync",
            [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_int,
                ctypes.c_void_p,
            ],
            ctypes.c_int,
        )
        self._memcpy = loaded_runtime.bind(
            "hipMemcpy",
            [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.c_int,
            ],
            ctypes.c_int,
        )
        self._copy_audit_v1 = _BoundHipCopyAuditStateV1()
        self._blocking_d2h_copy = _BoundBlockingD2HCopy(
            self._memcpy,
            loaded_runtime,
            self._copy_audit_v1,
        )
        self._stream_sync = loaded_runtime.bind(
            "hipStreamSynchronize", [ctypes.c_void_p], ctypes.c_int
        )

    @property
    def loaded_runtime(self) -> Any:
        """Return the exact process-local runtime used for every HIP binding."""

        return self._loaded

    @property
    def runtime_library_identity(self) -> Any:
        return self._loaded.library_identity

    @property
    def device_ordinal(self) -> int | None:
        """Return the last device ordinal selected successfully by this owner."""

        return self._device_ordinal

    def _check(self, status: int, where: str) -> None:
        if status != 0:
            detail = self._loaded.hip_error_string(status)
            raise HipContextError("hip_device_access_failed", f"{where}: {detail}")

    def set_device(self, ordinal: int) -> None:
        self._check(self._set_device(ordinal), "hipSetDevice")
        self._device_ordinal = ordinal

    def mem_info(self) -> tuple[int, int]:
        free = ctypes.c_size_t()
        total = ctypes.c_size_t()
        self._check(
            self._mem_info(ctypes.byref(free), ctypes.byref(total)),
            "hipMemGetInfo",
        )
        return int(free.value), int(total.value)

    def create_stream(self) -> ctypes.c_void_p:
        stream = ctypes.c_void_p()
        self._check(
            self._stream_create(ctypes.byref(stream), 1),
            "hipStreamCreateWithFlags",
        )
        return stream

    def malloc(self, byte_length: int) -> ctypes.c_void_p:
        pointer = ctypes.c_void_p()
        status = self._malloc(ctypes.byref(pointer), byte_length)
        if status != 0:
            raise HipContextError(
                "hip_allocation_failed",
                f"hipMalloc({byte_length}): {self._loaded.hip_error_string(status)}",
            )
        return pointer

    def copy_h2d_async(
        self, pointer: ctypes.c_void_p, array: np.ndarray, stream: ctypes.c_void_p
    ) -> None:
        byte_count = int(array.nbytes)
        ticket = self._copy_audit_v1.begin("h2d_async", byte_count)
        try:
            status = self._memcpy_async(
                pointer,
                ctypes.c_void_p(int(array.ctypes.data)),
                byte_count,
                1,
                stream,
            )
        except BaseException:
            self._copy_audit_v1.finish(ticket, succeeded=False)
            raise
        self._copy_audit_v1.finish(ticket, succeeded=status == 0)
        if status != 0:
            raise HipContextError(
                "hip_copy_failed",
                f"hipMemcpyAsync(H2D): {self._loaded.hip_error_string(status)}",
            )

    def copy_d2h_async(
        self, array: np.ndarray, pointer: ctypes.c_void_p, stream: ctypes.c_void_p
    ) -> None:
        byte_count = int(array.nbytes)
        ticket = self._copy_audit_v1.begin("d2h_async", byte_count)
        try:
            status = self._memcpy_async(
                ctypes.c_void_p(int(array.ctypes.data)),
                pointer,
                byte_count,
                2,
                stream,
            )
        except BaseException:
            self._copy_audit_v1.finish(ticket, succeeded=False)
            raise
        self._copy_audit_v1.finish(ticket, succeeded=status == 0)
        if status != 0:
            raise HipContextError(
                "hip_copy_failed",
                f"hipMemcpyAsync(D2H): {self._loaded.hip_error_string(status)}",
            )

    def copy_d2h(self, array: np.ndarray, pointer: ctypes.c_void_p) -> None:
        """Complete one blocking D2H copy before returning to the caller."""

        self._blocking_d2h_copy(array, pointer)

    def completion_export_copy_binding(self) -> _BoundBlockingD2HCopy:
        """Return the loader-bound immutable blocking D2H callable."""

        return self._blocking_d2h_copy

    def _bound_copy_audit_snapshot_v1(
        self,
        mint: object,
    ) -> tuple[_BoundHipCopyAuditStateV1, Any]:
        """Return a private immutable snapshot to the FGMRES audit composer."""

        if mint is not _BOUND_COPY_AUDIT_SNAPSHOT_MINT_V1:
            raise PermissionError("bound-copy audit snapshot authority is invalid")
        return self._copy_audit_v1, self._copy_audit_v1.snapshot()

    def synchronize(self, stream: ctypes.c_void_p) -> None:
        self._check(self._stream_sync(stream), "hipStreamSynchronize")

    def free(self, pointer: ctypes.c_void_p) -> None:
        self._check(self._free(pointer), "hipFree")

    def destroy_stream(self, stream: ctypes.c_void_p) -> None:
        self._check(self._stream_destroy(stream), "hipStreamDestroy")


class DeviceExecutionContext:
    """RAII owner of persistent, read-only HIP model-buffer allocations."""

    def __init__(
        self,
        *,
        buffers: SolverModelBuffers,
        capability_receipt: HipCapabilityReceipt,
        runtime: HipContextRuntimeProtocol,
        device: HipDeviceContextIdentity | None,
        context_id: str,
        stream: Any,
        pointers: dict[str, Any],
        buffer_views: tuple[HipBufferView, ...],
        telemetry: HipContextTelemetry,
        cleanup_only_reason: HipContextReason | None = None,
    ) -> None:
        self._buffers = buffers
        self._capability_receipt = capability_receipt
        self._runtime = runtime
        self._device = device
        self._context_id = context_id
        self._stream = stream
        self._pointers = pointers
        self._buffer_views = buffer_views
        self._telemetry = telemetry
        self._cleanup_only_reason = cleanup_only_reason
        self._closed = False
        self._close_failed = False

    def __repr__(self) -> str:
        status = (
            "cleanup_only"
            if self._cleanup_only_reason is not None and not self._closed
            else (
                "close_failed"
                if self._close_failed
                else ("closed" if self._closed else "ready")
            )
        )
        return f"DeviceExecutionContext(context_id={self._context_id!r}, status={status!r})"

    def __enter__(self) -> DeviceExecutionContext:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best-effort interpreter cleanup
        try:
            self.close()
        except Exception:
            pass

    @property
    def context_id(self) -> str:
        return self._context_id

    @property
    def closed(self) -> bool:
        return self._closed

    def buffer(self, name: str) -> HipBufferView:
        self._require_open()
        for view in self._buffer_views:
            if view.name == name:
                return view
        raise KeyError(f"Unknown HIP buffer view: {name}")

    def receipt(self) -> HipContextReceipt:
        if self._cleanup_only_reason is not None:
            return _build_unavailable_receipt(
                self._buffers,
                self._capability_receipt,
                self._context_id,
                self._cleanup_only_reason,
                telemetry=self._telemetry,
            )
        if self._close_failed:
            raise HipContextError(
                "hip_context_close_failed",
                "No closed receipt is available because device cleanup failed.",
            )
        return _build_context_receipt(
            status="context_closed" if self._closed else "context_ready",
            context_id=self._context_id,
            capability_receipt=self._capability_receipt,
            buffers=self._buffers,
            actual_backend="hip",
            reason=None,
            device=self._device,
            buffer_views=self._buffer_views,
            telemetry=self._telemetry,
            resident=not self._closed,
        )

    def export_for_verification(self, name: str) -> np.ndarray:
        """Explicitly download one buffer and account for the D2H operation."""

        view = self.buffer(name)
        descriptor = next(
            row for row in self._buffers.descriptors if row.name == view.name
        )
        host = np.empty(descriptor.shape, dtype=descriptor.dtype, order="C")
        try:
            self._runtime.copy_d2h_async(host, self._pointers[view.name], self._stream)
            self._runtime.synchronize(self._stream)
        except HipContextError:
            raise
        except Exception as exc:
            raise HipContextError("hip_copy_failed", str(exc)) from exc
        downloaded = immutable_array(host, dtype=descriptor.dtype)
        if array_data_hash(downloaded) != descriptor.data_hash:
            raise HipContextError(
                "hip_copy_failed",
                f"Verification download hash mismatch for {name}.",
            )
        self._telemetry = replace(
            self._telemetry,
            d2h_bytes=self._telemetry.d2h_bytes + descriptor.byte_length,
            d2h_operation_count=self._telemetry.d2h_operation_count + 1,
            explicit_sync_count=self._telemetry.explicit_sync_count + 1,
        )
        return downloaded

    def close(self) -> None:
        if self._closed:
            return
        first_error: Exception | None = None
        deallocated = 0
        for name in reversed(tuple(self._pointers)):
            try:
                self._runtime.free(self._pointers[name])
                deallocated += 1
            except Exception as exc:  # pragma: no cover - hardware failure path
                if first_error is None:
                    first_error = exc
                continue
            del self._pointers[name]
            byte_length = next(
                row.byte_length for row in self._buffers.descriptors if row.name == name
            )
            self._telemetry = replace(
                self._telemetry,
                current_device_payload_bytes=(
                    self._telemetry.current_device_payload_bytes - byte_length
                ),
            )
        self._telemetry = replace(
            self._telemetry,
            deallocation_count=self._telemetry.deallocation_count + deallocated,
        )
        # A stream remains the ownership anchor for any allocation whose free
        # failed.  Destroying it and clearing the pointer map would make the
        # leak unreachable and make close retry impossible.
        if self._pointers:
            self._close_failed = True
            raise HipContextError(
                "hip_device_access_failed",
                str(first_error or "HIP allocations remain after close."),
            )
        if self._stream is not None:
            try:
                self._runtime.destroy_stream(self._stream)
            except Exception as exc:  # pragma: no cover - hardware failure path
                self._close_failed = True
                raise HipContextError("hip_device_access_failed", str(exc)) from exc
            self._stream = None
        self._closed = True
        self._close_failed = False
        self._telemetry = replace(
            self._telemetry,
            current_device_payload_bytes=0,
        )
        if self._cleanup_only_reason is not None:
            original_detail = self._cleanup_only_reason.detail.split(
                "; cleanup incomplete:", 1
            )[0]
            self._cleanup_only_reason = HipContextReason(
                self._cleanup_only_reason.code,
                _bounded_detail(f"{original_detail}; cleanup recovered"),
            )
        if first_error is not None:
            # Defensive: all failed frees necessarily leave entries above.
            raise HipContextError("hip_device_access_failed", str(first_error))

    def _require_open(self) -> None:
        if self._closed:
            raise HipContextError("hip_context_closed", "Context is closed.")
        if self._cleanup_only_reason is not None:
            raise HipContextError(
                "hip_context_cleanup_only",
                "Context owns failed-open resources and permits close() only.",
            )
        if self._close_failed:
            raise HipContextError(
                "hip_context_close_failed",
                "Context is cleanup-only after a failed close; retry close().",
            )


def open_device_execution_context(
    buffers: SolverModelBuffers,
    *,
    device_ordinal: int = 0,
    runtime_library: str | Path | None = None,
    memory_budget_bytes: int | None = None,
    runtime: Any | None = None,
) -> HipContextOpenResult:
    """Upload every ModelBuffer exactly once or return an unavailable receipt."""

    validate_solver_model_buffers(buffers)
    if isinstance(device_ordinal, bool) or not isinstance(device_ordinal, int):
        raise HipContextError(
            "hip_device_ordinal_invalid", "device_ordinal must be an integer."
        )
    if memory_budget_bytes is not None and (
        isinstance(memory_budget_bytes, bool)
        or not isinstance(memory_budget_bytes, int)
        or memory_budget_bytes <= 0
    ):
        raise HipContextError(
            "hip_memory_budget_invalid",
            "memory_budget_bytes must be a positive integer.",
        )
    capability = probe_hip_capability(
        runtime_library=runtime_library,
        device_ordinal=device_ordinal,
        runtime=runtime,
    )
    context_id = _context_id(buffers, capability, device_ordinal)
    if capability.status != "ready":
        reason = _capability_reason(capability)
        receipt = _build_unavailable_receipt(buffers, capability, context_id, reason)
        return HipContextOpenResult(None, capability, receipt)

    total_payload_bytes = sum(row.byte_length for row in buffers.descriptors)
    if memory_budget_bytes is not None and total_payload_bytes > memory_budget_bytes:
        reason = HipContextReason(
            "hip_memory_budget_exceeded",
            f"Required {total_payload_bytes} bytes exceeds budget {memory_budget_bytes}.",
        )
        receipt = _build_unavailable_receipt(buffers, capability, context_id, reason)
        return HipContextOpenResult(None, capability, receipt)

    context_runtime: HipContextRuntimeProtocol
    if runtime is None:
        loaded = load_hip_native_runtime(runtime_library=runtime_library)
        context_runtime = _BoundHipContextRuntime(loaded)
    elif hasattr(runtime, "bind"):
        context_runtime = _BoundHipContextRuntime(runtime)
    else:
        context_runtime = runtime

    pointers: dict[str, Any] = {}
    stream: Any | None = None
    views: list[HipBufferView] = []
    telemetry = HipContextTelemetry(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    try:
        context_runtime.set_device(device_ordinal)
        free_before, total_memory = context_runtime.mem_info()
        stream = context_runtime.create_stream()
        for descriptor in buffers.descriptors:
            array = buffers.array(descriptor.name)
            pointer = context_runtime.malloc(descriptor.byte_length)
            pointers[descriptor.name] = pointer
            telemetry = replace(
                telemetry,
                allocation_count=telemetry.allocation_count + 1,
                current_device_payload_bytes=(
                    telemetry.current_device_payload_bytes + descriptor.byte_length
                ),
                peak_device_payload_bytes=(
                    telemetry.peak_device_payload_bytes + descriptor.byte_length
                ),
            )
            context_runtime.copy_h2d_async(pointer, array, stream)
            telemetry = replace(
                telemetry,
                h2d_bytes=telemetry.h2d_bytes + descriptor.byte_length,
                h2d_operation_count=telemetry.h2d_operation_count + 1,
            )
            views.append(_buffer_view(descriptor, device_ordinal))
        context_runtime.synchronize(stream)
        telemetry = replace(
            telemetry, explicit_sync_count=telemetry.explicit_sync_count + 1
        )
        free_after, total_after = context_runtime.mem_info()
        if total_after != total_memory:
            raise HipContextError(
                "hip_device_access_failed", "Device total memory changed during upload."
            )
        device = HipDeviceContextIdentity(
            ordinal=device_ordinal,
            name=str(capability.device.name),
            architecture=None,
            runtime_version_raw=int(capability.versions.runtime),
            driver_version_raw=int(capability.versions.driver),
            total_memory_bytes=total_memory,
            free_memory_bytes_before_upload=free_before,
            free_memory_bytes_after_upload=free_after,
        )
        context = DeviceExecutionContext(
            buffers=buffers,
            capability_receipt=capability,
            runtime=context_runtime,
            device=device,
            context_id=context_id,
            stream=stream,
            pointers=pointers,
            buffer_views=tuple(views),
            telemetry=telemetry,
        )
        receipt = context.receipt()
        return HipContextOpenResult(context, capability, receipt)
    except Exception as exc:
        code = (
            exc.code if isinstance(exc, HipContextError) else "hip_device_access_failed"
        )
        if code not in _CONTEXT_REASON_CODES:
            code = "hip_device_access_failed"
        deallocated = 0
        cleanup_error: Exception | None = None
        for name in reversed(tuple(pointers)):
            byte_length = next(
                row.byte_length for row in buffers.descriptors if row.name == name
            )
            try:
                context_runtime.free(pointers[name])
            except Exception as cleanup_exc:
                if cleanup_error is None:
                    cleanup_error = cleanup_exc
                continue
            del pointers[name]
            deallocated += 1
            telemetry = replace(
                telemetry,
                current_device_payload_bytes=(
                    telemetry.current_device_payload_bytes - byte_length
                ),
            )
        if not pointers and stream is not None:
            try:
                context_runtime.destroy_stream(stream)
            except Exception as cleanup_exc:
                if cleanup_error is None:
                    cleanup_error = cleanup_exc
            else:
                stream = None
        telemetry = replace(
            telemetry,
            deallocation_count=telemetry.deallocation_count + deallocated,
        )
        reason = HipContextReason(code, _bounded_detail(str(exc)))
        if cleanup_error is not None or pointers or stream is not None:
            cleanup_reason = HipContextReason(
                code,
                _bounded_detail(f"{exc}; cleanup incomplete: {cleanup_error}"),
            )
            cleanup_owner = DeviceExecutionContext(
                buffers=buffers,
                capability_receipt=capability,
                runtime=context_runtime,
                device=None,
                context_id=context_id,
                stream=stream,
                pointers=pointers,
                buffer_views=(),
                telemetry=telemetry,
                cleanup_only_reason=cleanup_reason,
            )
            return HipContextOpenResult(
                cleanup_owner,
                capability,
                cleanup_owner.receipt(),
            )
        receipt = _build_unavailable_receipt(
            buffers, capability, context_id, reason, telemetry=telemetry
        )
        return HipContextOpenResult(None, capability, receipt)


def validate_hip_context_receipt(
    receipt: HipContextReceipt,
    *,
    expected_buffers: SolverModelBuffers | None = None,
) -> HipContextReceipt:
    if not isinstance(receipt, HipContextReceipt):
        raise HipContextError(
            "hip_context_receipt_type_invalid", "Expected HipContextReceipt."
        )
    payload = _context_payload(receipt, include_hash=True)
    errors = sorted(
        _context_schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise HipContextError(
            "hip_context_receipt_schema_invalid", f"{path}: {error.message}"
        )
    expected_hash = canonical_hash(_context_payload(receipt, include_hash=False))
    if receipt.context_receipt_hash != expected_hash:
        raise HipContextError(
            "hip_context_receipt_hash_mismatch", "Context receipt hash is stale."
        )
    if (
        receipt.telemetry.kernel_launch_count != 0
        or receipt.telemetry.fallback_count != 0
    ):
        raise HipContextError(
            "hip_context_claim_invalid", "Kernel/fallback count must remain zero."
        )
    if any(
        (
            receipt.claims.operator_bound,
            receipt.claims.state_bound,
            receipt.claims.residual_jvp_ready,
            receipt.claims.solver_ready,
            receipt.claims.device_resident_newton_krylov,
            receipt.claims.cpu_hip_parity_proven,
            receipt.claims.commercial_readiness,
        )
    ):
        raise HipContextError(
            "hip_context_claim_invalid",
            "Context foundation cannot assert solver claims.",
        )
    if receipt.status in ("context_ready", "context_closed"):
        names = tuple(view.name for view in receipt.buffer_views)
        if len(names) != 16 or len(set(names)) != 16 or names != tuple(sorted(names)):
            raise HipContextError(
                "hip_context_buffer_views_invalid",
                "Context receipt requires the 16 canonical buffer views once each.",
            )
        total_bytes = sum(view.byte_length for view in receipt.buffer_views)
        if (
            receipt.telemetry.h2d_bytes != total_bytes
            or receipt.telemetry.h2d_operation_count != len(receipt.buffer_views)
            or receipt.telemetry.allocation_count != len(receipt.buffer_views)
            or receipt.telemetry.peak_device_payload_bytes != total_bytes
        ):
            raise HipContextError(
                "hip_context_telemetry_invalid",
                "Initial upload counters do not match buffer descriptors.",
            )
        expected_current = total_bytes if receipt.status == "context_ready" else 0
        if receipt.telemetry.current_device_payload_bytes != expected_current:
            raise HipContextError(
                "hip_context_telemetry_invalid",
                "Current device bytes do not match context status.",
            )
    if expected_buffers is not None:
        validate_solver_model_buffers(expected_buffers)
        expected_binding = _buffer_binding(expected_buffers)
        if receipt.solver_model_buffers != expected_binding:
            raise HipContextError(
                "hip_context_buffer_binding_mismatch",
                "Receipt is bound to different SolverModelBuffers.",
            )
        descriptors = {row.name: row for row in expected_buffers.descriptors}
        for view in receipt.buffer_views:
            row = descriptors[view.name]
            if (
                view.dtype != row.dtype
                or view.shape != row.shape
                or view.byte_length != row.byte_length
                or view.data_hash != row.data_hash
                or view.content_hash != row.content_hash
            ):
                raise HipContextError(
                    "hip_context_buffer_view_mismatch",
                    f"Device BufferView {view.name} differs from its host descriptor.",
                )
    forbidden = ("pointer", "address", "stream", "handle")
    if _has_forbidden_runtime_key(payload, forbidden):
        raise HipContextError(
            "hip_context_runtime_handle_leak",
            "Serialized context receipt contains a runtime handle term.",
        )
    return receipt


def _context_payload(
    receipt: HipContextReceipt, *, include_hash: bool
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": HIP_CONTEXT_RECEIPT_SCHEMA_VERSION,
        "capability_profile": HIP_CONTEXT_CAPABILITY_PROFILE,
        "status": receipt.status,
        "context_id": receipt.context_id,
        "requested_backend": "hip",
        "actual_backend": receipt.actual_backend,
        "fallback_policy": "forbidden",
        "fallback_used": False,
        "reason": None if receipt.reason is None else receipt.reason.to_dict(),
        "capability_receipt_hash": receipt.capability_receipt_hash,
        "solver_model_buffers": receipt.solver_model_buffers.to_dict(),
        "device": None if receipt.device is None else receipt.device.to_dict(),
        "buffer_views": [view.to_dict() for view in receipt.buffer_views],
        "telemetry": receipt.telemetry.to_dict(),
        "claims": receipt.claims.to_dict(),
        "extensions": {},
    }
    if include_hash:
        payload["context_receipt_hash"] = receipt.context_receipt_hash
    return payload


def _build_context_receipt(
    *,
    status: str,
    context_id: str,
    capability_receipt: HipCapabilityReceipt,
    buffers: SolverModelBuffers,
    actual_backend: str | None,
    reason: HipContextReason | None,
    device: HipDeviceContextIdentity | None,
    buffer_views: tuple[HipBufferView, ...],
    telemetry: HipContextTelemetry,
    resident: bool,
) -> HipContextReceipt:
    draft = HipContextReceipt(
        status=status,
        context_id=context_id,
        actual_backend=actual_backend,
        reason=reason,
        capability_receipt_hash=capability_receipt.receipt_hash,
        solver_model_buffers=_buffer_binding(buffers),
        device=device,
        buffer_views=buffer_views,
        telemetry=telemetry,
        claims=HipContextClaims(model_buffers_device_resident=resident),
        context_receipt_hash="sha256:" + ("0" * 64),
    )
    receipt = replace(
        draft,
        context_receipt_hash=canonical_hash(
            _context_payload(draft, include_hash=False)
        ),
    )
    return validate_hip_context_receipt(receipt, expected_buffers=buffers)


def _build_unavailable_receipt(
    buffers: SolverModelBuffers,
    capability: HipCapabilityReceipt,
    context_id: str,
    reason: HipContextReason,
    *,
    telemetry: HipContextTelemetry | None = None,
) -> HipContextReceipt:
    return _build_context_receipt(
        status="unavailable",
        context_id=context_id,
        capability_receipt=capability,
        buffers=buffers,
        actual_backend=None,
        reason=reason,
        device=None,
        buffer_views=(),
        telemetry=(
            HipContextTelemetry(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
            if telemetry is None
            else telemetry
        ),
        resident=False,
    )


def _buffer_binding(buffers: SolverModelBuffers) -> HipBufferBinding:
    return HipBufferBinding(
        schema_version=buffers.schema_version,
        model_ir_content_hash=buffers.model_ir_content_hash,
        load_pattern_id=buffers.load_pattern_id,
        numeric_buffer_hash=buffers.numeric_buffer_hash,
        entity_mapping_hash=buffers.entity_mapping_hash,
        artifact_hash=buffers.artifact_hash,
    )


def _buffer_view(descriptor: Any, ordinal: int) -> HipBufferView:
    return HipBufferView(
        name=descriptor.name,
        dtype=descriptor.dtype,
        shape=descriptor.shape,
        layout="C",
        byte_length=descriptor.byte_length,
        data_hash=descriptor.data_hash,
        content_hash=descriptor.content_hash,
        memory_space="hip_device",
        device_ordinal=ordinal,
        access="read_only",
        initial_transfer="async_h2d_then_explicit_sync",
    )


def _context_id(
    buffers: SolverModelBuffers,
    capability: HipCapabilityReceipt,
    ordinal: int,
) -> str:
    digest = canonical_hash(
        {
            "solver_artifact_hash": buffers.artifact_hash,
            "capability_receipt_hash": capability.receipt_hash,
            "device_ordinal": ordinal,
        }
    )
    return f"HipContext:{digest.removeprefix('sha256:')[:24]}"


def _capability_reason(capability: HipCapabilityReceipt) -> HipContextReason:
    mapping = {
        "hip_runtime_library_not_found": "hip_native_library_missing",
        "hip_runtime_library_hash_failed": "hip_native_library_missing",
        "hip_runtime_library_load_failed": "hip_native_library_missing",
        "hip_runtime_symbol_missing": "hip_native_abi_mismatch",
        "hip_init_failed": "hip_runtime_init_failed",
        "hip_device_count_failed": "hip_device_access_failed",
        "hip_no_devices": "hip_no_device",
        "hip_device_ordinal_unavailable": "hip_device_ordinal_invalid",
        "hip_device_name_failed": "hip_device_access_failed",
        "hip_device_name_invalid": "hip_device_access_failed",
        "hip_runtime_version_failed": "hip_device_access_failed",
        "hip_driver_version_failed": "hip_device_access_failed",
    }
    return HipContextReason(
        mapping.get(capability.status_code, "hip_device_access_failed"),
        _bounded_detail(capability.message),
    )


def _bounded_detail(value: str) -> str:
    normalized = " ".join(value.split()) or "HIP context unavailable."
    return normalized[:512]


def _has_forbidden_runtime_key(value: Any, forbidden: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in forbidden)
            or _has_forbidden_runtime_key(item, forbidden)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_forbidden_runtime_key(item, forbidden) for item in value)
    return False


@lru_cache(maxsize=1)
def _context_schema_validator() -> Draft202012Validator:
    path = (
        Path(__file__).resolve().parents[3]
        / "schemas"
        / "hip_context_receipt_v1.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "HIP_CONTEXT_CAPABILITY_PROFILE",
    "HIP_CONTEXT_RECEIPT_SCHEMA_VERSION",
    "DeviceExecutionContext",
    "HipBufferView",
    "HipContextError",
    "HipFreeKnownNotFreedError",
    "HipFreeOutcomeUncertainError",
    "HipContextOpenResult",
    "HipContextReceipt",
    "open_device_execution_context",
    "validate_hip_context_receipt",
]
