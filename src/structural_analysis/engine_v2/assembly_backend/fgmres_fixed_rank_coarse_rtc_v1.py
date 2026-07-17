"""Fixed-source HIPRTC owner for the FGMRES fixed-rank coarse application.

The loaded four-symbol module consumes the buffer layout compiled by
``fgmres_fixed_rank_coarse_plan_v1``.  It tracks every accepted launch until an
external same-stream fence is acknowledged.  It does not allocate buffers,
copy data, synchronize a stream, or integrate the recurrence state machine.
"""

from __future__ import annotations

import ctypes
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, replace
from functools import wraps
from pathlib import Path
import threading
from typing import Any
import weakref

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

from .fgmres_fixed_rank_coarse_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_APPLY_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_PREPARE_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
    hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1,
)
from .fgmres_plan import HIP_FGMRES_MAX_RESTART_DIMENSION


HIP_RTC_FGMRES_FIXED_RANK_COARSE_IDENTITY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-rtc-fgmres-fixed-rank-coarse-identity.v1"
)
HIP_RTC_FGMRES_FIXED_RANK_COARSE_ABI_VERSION_V1 = 1
HIP_RTC_FGMRES_FIXED_RANK_COARSE_KERNEL_NAME_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_v1"
)

_SOURCE_RESOURCE = "kernels/engine_v2_fgmres_fixed_rank_coarse_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17", "-ffp-contract=off")
_INT32_MAX = (1 << 31) - 1
_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
_FP64_BYTE_LENGTH = 8
_U32_BYTE_LENGTH = 4
_KERNEL_MINT = object()


class _HipRtcFgmresFixedRankCoarseKernelHandoffV1:
    """One-shot strong owner for an internally compiled coarse kernel."""

    __slots__ = ("_kernel", "_lock", "_publication_state", "__weakref__")

    def __init__(self) -> None:
        self._kernel: HipRtcFgmresFixedRankCoarseKernelV1 | None = None
        self._lock = threading.RLock()
        self._publication_state = "empty"

    @property
    def kernel(self) -> HipRtcFgmresFixedRankCoarseKernelV1 | None:
        with self._lock:
            if self._publication_state != "published":
                return None
            return self._kernel

    @property
    def occupied(self) -> bool:
        with self._lock:
            return self._publication_state != "empty"

    def publish(self, kernel: HipRtcFgmresFixedRankCoarseKernelV1) -> None:
        with self._lock:
            if (
                self._publication_state != "empty"
                or self._kernel is not None
                or type(kernel) is not HipRtcFgmresFixedRankCoarseKernelV1
                or kernel.closed
            ):
                raise HipRtcFgmresFixedRankCoarseV1Error(
                    "hip_rtc_fgmres_coarse_kernel_handoff_invalid",
                    "The handoff accepts one exact live coarse kernel.",
                )
            self._publication_state = "reserved"
            try:
                self._kernel = kernel
                self._publication_state = "published"
            except BaseException:
                self._publication_state = "spent"
                raise


class _HipRtcFgmresFixedRankCoarseKernelHandoffFrameV1:
    """One-shot weak task-local route that owns no native resource."""

    __slots__ = ("_target_refs",)

    def __init__(
        self,
        target: _HipRtcFgmresFixedRankCoarseKernelHandoffV1,
    ) -> None:
        self._target_refs = [weakref.ref(target)]

    def claim(self) -> _HipRtcFgmresFixedRankCoarseKernelHandoffV1 | None:
        try:
            target_ref = self._target_refs.pop()
        except IndexError:
            return None
        return target_ref()

    def disarm(self) -> None:
        self._target_refs.clear()


_KERNEL_HANDOFF_V1: ContextVar[
    _HipRtcFgmresFixedRankCoarseKernelHandoffFrameV1 | None
] = ContextVar(
    "engine_v2_fgmres_fixed_rank_coarse_kernel_handoff_v1",
    default=None,
)


def _serialize_kernel_operation(method: Any) -> Any:
    @wraps(method)
    def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        with self._operation_lock:
            if self._operation_active:
                _fail(
                    "hip_rtc_fgmres_coarse_reentrant_operation",
                    "Reentrant coarse module operations are not allowed.",
                    disposition="not_attempted",
                    kernel=self,
                )
            self._operation_active = True
            try:
                return method(self, *args, **kwargs)
            finally:
                self._operation_active = False

    return wrapped


class HipRtcFgmresFixedRankCoarseV1Error(HipRtcError):
    """Stable module error with native launch acceptance information."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        compile_log: str = "",
        launch_disposition: str | None = None,
        attempted_launch_count: int | None = None,
        accepted_launch_count: int | None = None,
    ) -> None:
        if launch_disposition not in {
            None,
            "not_attempted",
            "rejected",
            "ambiguous",
        }:
            raise ValueError("launch_disposition is invalid")
        self.launch_disposition = launch_disposition
        self.attempted_launch_count = attempted_launch_count
        self.accepted_launch_count = accepted_launch_count
        super().__init__(code, message, compile_log=compile_log)


@dataclass(frozen=True, slots=True)
class HipRtcFgmresFixedRankCoarseKernelIdentityV1:
    schema_version: str
    abi_version: int
    application_abi_version: int
    kernel_name: str
    prepare_symbol: str
    dot_symbol: str
    solve_symbol: str
    apply_symbol: str
    vector_block_size: int
    maximum_rank: int
    kernel_abi_hash: str
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
    def kernel_symbols(self) -> tuple[str, str, str, str]:
        return (
            self.prepare_symbol,
            self.dot_symbol,
            self.solve_symbol,
            self.apply_symbol,
        )

    def to_dict(self) -> dict[str, Any]:
        validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class HipRtcFgmresFixedRankCoarseKernelV1:
    """Loaded four-symbol module with same-stream pending-work ownership."""

    __slots__ = (
        "_runtime",
        "_module",
        "_functions",
        "_identity",
        "_operation_lock",
        "_operation_active",
        "_closed",
        "_unload_disposition",
        "_pending_stream_pointer",
        "_pending_accepted_launch_count",
        "_pending_uncertain",
        "_lifetime_attempted_launch_count",
        "_lifetime_accepted_launch_count",
    )

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        functions: dict[str, ctypes.c_void_p],
        identity: HipRtcFgmresFixedRankCoarseKernelIdentityV1,
        _mint: object | None = None,
    ) -> None:
        if _mint is not _KERNEL_MINT:
            raise TypeError("coarse kernels are fixed-source compiler issued only")
        if tuple(functions) != HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1:
            raise HipRtcFgmresFixedRankCoarseV1Error(
                "hip_rtc_fgmres_coarse_binding_invalid",
                "The exact four-symbol binding set is required.",
            )
        validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1(identity)
        self._runtime = runtime
        self._module = module
        self._functions = dict(functions)
        self._identity = identity
        self._operation_lock = threading.RLock()
        self._operation_active = False
        self._closed = False
        self._unload_disposition = "live"
        self._pending_stream_pointer: int | None = None
        self._pending_accepted_launch_count = 0
        self._pending_uncertain = False
        self._lifetime_attempted_launch_count = 0
        self._lifetime_accepted_launch_count = 0

    @property
    def identity(self) -> HipRtcFgmresFixedRankCoarseKernelIdentityV1:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def unload_disposition(self) -> str:
        return self._unload_disposition

    @property
    def pending(self) -> bool:
        return self._pending_accepted_launch_count > 0 or self._pending_uncertain

    @property
    def pending_accepted_launch_count(self) -> int:
        return self._pending_accepted_launch_count

    @property
    def lifetime_attempted_launch_count(self) -> int:
        return self._lifetime_attempted_launch_count

    @property
    def lifetime_accepted_launch_count(self) -> int:
        return self._lifetime_accepted_launch_count

    @_serialize_kernel_operation
    def launch_application(
        self,
        *,
        stream: Any,
        free_dof_count: int,
        retained_rank: int,
        restart_dimension: int,
        logical_index: int,
        jacobi_inverse: Any,
        basis_v: Any,
        preconditioned_basis_z: Any,
        coarse_physical_basis_z: Any,
        coarse_operator_basis_az: Any,
        coarse_cholesky_l: Any,
        coarse_rhs: Any,
        coarse_coefficients: Any,
        coarse_status: Any,
    ) -> int:
        """Enqueue exactly four ordered kernels and return accepted delta."""

        self._require_open()
        f, k, m, logical = _dimensions(
            free_dof_count,
            retained_rank,
            restart_dimension,
            logical_index,
        )
        pointers = _buffer_pointer_arguments(
            (
                (
                    "jacobi_inverse",
                    jacobi_inverse,
                    f * _FP64_BYTE_LENGTH,
                    _FP64_BYTE_LENGTH,
                ),
                (
                    "basis_v",
                    basis_v,
                    (m + 1) * f * _FP64_BYTE_LENGTH,
                    _FP64_BYTE_LENGTH,
                ),
                (
                    "preconditioned_basis_z",
                    preconditioned_basis_z,
                    m * f * _FP64_BYTE_LENGTH,
                    _FP64_BYTE_LENGTH,
                ),
                (
                    "coarse_physical_basis_z",
                    coarse_physical_basis_z,
                    f * k * _FP64_BYTE_LENGTH,
                    _FP64_BYTE_LENGTH,
                ),
                (
                    "coarse_operator_basis_az",
                    coarse_operator_basis_az,
                    f * k * _FP64_BYTE_LENGTH,
                    _FP64_BYTE_LENGTH,
                ),
                (
                    "coarse_cholesky_l",
                    coarse_cholesky_l,
                    k * k * _FP64_BYTE_LENGTH,
                    _FP64_BYTE_LENGTH,
                ),
                ("coarse_rhs", coarse_rhs, k * _FP64_BYTE_LENGTH, 8),
                (
                    "coarse_coefficients",
                    coarse_coefficients,
                    k * _FP64_BYTE_LENGTH,
                    _FP64_BYTE_LENGTH,
                ),
                ("coarse_status", coarse_status, _U32_BYTE_LENGTH, 4),
            )
        )
        (
            inverse_pointer,
            basis_v_pointer,
            basis_z_pointer,
            physical_pointer,
            operator_pointer,
            cholesky_pointer,
            rhs_pointer,
            coefficients_pointer,
            status_pointer,
        ) = pointers
        accepted_before = self._lifetime_accepted_launch_count
        common_scalars = (f, k, m, logical)
        self._launch(
            HIP_FGMRES_FIXED_RANK_COARSE_PREPARE_SYMBOL_V1,
            stream=stream,
            grid_x=1,
            block_x=1,
            scalar_values=common_scalars,
            pointer_values=(rhs_pointer, coefficients_pointer, status_pointer),
            operation="coarse prepare",
        )
        self._launch(
            HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
            stream=stream,
            grid_x=k,
            block_x=HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
            scalar_values=common_scalars,
            pointer_values=(
                basis_v_pointer,
                physical_pointer,
                rhs_pointer,
                status_pointer,
            ),
            operation="coarse dot",
        )
        self._launch(
            HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
            stream=stream,
            grid_x=1,
            block_x=1,
            scalar_values=(k,),
            pointer_values=(
                cholesky_pointer,
                rhs_pointer,
                coefficients_pointer,
                status_pointer,
            ),
            operation="coarse Cholesky solve",
        )
        self._launch(
            HIP_FGMRES_FIXED_RANK_COARSE_APPLY_SYMBOL_V1,
            stream=stream,
            grid_x=(f + HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1 - 1)
            // HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
            block_x=HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
            scalar_values=common_scalars,
            pointer_values=(
                inverse_pointer,
                basis_v_pointer,
                basis_z_pointer,
                physical_pointer,
                operator_pointer,
                coefficients_pointer,
                status_pointer,
            ),
            operation="coarse plus Jacobi apply",
        )
        accepted = self._lifetime_accepted_launch_count - accepted_before
        if accepted != 4:
            _fail(
                "hip_rtc_fgmres_coarse_launch_count_invalid",
                "One application must accept exactly four launches.",
                disposition="ambiguous",
                kernel=self,
            )
        return accepted

    @_serialize_kernel_operation
    def acknowledge_stream_fence(self, stream: Any) -> int:
        """Release pending work after the caller observes the exact stream fence."""

        self._require_open()
        stream_pointer = _runtime_pointer(stream, "stream")
        if self._pending_stream_pointer not in {None, stream_pointer}:
            _fail(
                "hip_rtc_fgmres_coarse_fence_stream_invalid",
                "Fence stream does not match the launch stream.",
                disposition="not_attempted",
                kernel=self,
            )
        acknowledged = self._pending_accepted_launch_count
        self._pending_stream_pointer = None
        self._pending_accepted_launch_count = 0
        self._pending_uncertain = False
        return acknowledged

    @_serialize_kernel_operation
    def close(self) -> None:
        if self._closed:
            return
        if self._unload_disposition == "terminal":
            self._closed = True
            return
        if self._unload_disposition == "external_unload_succeeded":
            self._finish_close()
            return
        if self._unload_disposition != "live":
            _fail(
                "hip_rtc_fgmres_coarse_module_unload_uncertain",
                "The module unload outcome is uncertain and cannot be retried.",
                disposition="not_attempted",
                kernel=self,
            )
        if self.pending:
            _fail(
                "hip_rtc_fgmres_coarse_pending_work",
                "The coarse module cannot unload before a same-stream fence.",
                disposition="not_attempted",
                kernel=self,
            )
        self._unload_disposition = "unload_call_inflight"
        try:
            status = int(self._runtime.unload(self._module))
            self._unload_disposition = (
                "external_unload_succeeded" if status == 0 else "live"
            )
        except BaseException as exc:
            self._unload_disposition = "unload_outcome_uncertain"
            if not isinstance(exc, Exception):
                raise
            raise HipRtcFgmresFixedRankCoarseV1Error(
                "hip_rtc_fgmres_coarse_module_unload_uncertain",
                f"hipModuleUnload raised {type(exc).__name__}; outcome is uncertain.",
            ) from exc
        if status != 0:
            raise HipRtcFgmresFixedRankCoarseV1Error(
                "hip_rtc_fgmres_coarse_module_unload_failed",
                "hipModuleUnload failed: " + self._runtime.error_string(status),
            )
        self._finish_close()

    def _finish_close(self) -> None:
        if self._unload_disposition != "external_unload_succeeded":
            raise RuntimeError("coarse module close finalization is not authorized")
        self._module = ctypes.c_void_p()
        self._functions = {}
        self._unload_disposition = "terminal"
        self._closed = True

    def _launch(
        self,
        symbol: str,
        *,
        stream: Any,
        grid_x: int,
        block_x: int,
        scalar_values: tuple[int, ...],
        pointer_values: tuple[int, ...],
        operation: str,
    ) -> None:
        self._require_open()
        stream_pointer = _runtime_pointer(stream, "stream")
        if self._pending_stream_pointer not in {None, stream_pointer}:
            _fail(
                "hip_rtc_fgmres_coarse_stream_changed",
                "All coarse launches must use one stream until fenced.",
                disposition="not_attempted",
                kernel=self,
            )
        function = self._functions.get(symbol)
        if type(function) is not ctypes.c_void_p or not function.value:
            _fail(
                "hip_rtc_fgmres_coarse_binding_changed",
                f"Fixed symbol binding is unavailable: {symbol}.",
                disposition="not_attempted",
                kernel=self,
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
        previous_stream_pointer = self._pending_stream_pointer
        previous_uncertain = self._pending_uncertain
        self._pending_stream_pointer = stream_pointer
        self._pending_uncertain = True
        self._lifetime_attempted_launch_count += 1
        try:
            status = int(
                self._runtime.launch(
                    function,
                    grid_x=grid_x,
                    block_x=block_x,
                    stream=ctypes.c_void_p(stream_pointer),
                    parameters=parameters,
                )
            )
        except BaseException as exc:
            if not isinstance(exc, Exception):
                raise
            raise HipRtcFgmresFixedRankCoarseV1Error(
                "hip_rtc_fgmres_coarse_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
                launch_disposition="ambiguous",
                attempted_launch_count=self._lifetime_attempted_launch_count,
                accepted_launch_count=self._lifetime_accepted_launch_count,
            ) from exc
        if status != 0:
            self._pending_stream_pointer = previous_stream_pointer
            self._pending_uncertain = previous_uncertain
            raise HipRtcFgmresFixedRankCoarseV1Error(
                "hip_rtc_fgmres_coarse_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel failed: "
                f"{self._runtime.error_string(status)}.",
                launch_disposition="rejected",
                attempted_launch_count=self._lifetime_attempted_launch_count,
                accepted_launch_count=self._lifetime_accepted_launch_count,
            )
        self._pending_accepted_launch_count += 1
        self._lifetime_accepted_launch_count += 1
        self._pending_uncertain = previous_uncertain

    def _require_open(self) -> None:
        if self._closed:
            _fail(
                "hip_rtc_fgmres_coarse_kernel_closed",
                "Coarse kernel is closed.",
                disposition="not_attempted",
                kernel=self,
            )
        if self._unload_disposition != "live":
            _fail(
                "hip_rtc_fgmres_coarse_module_state_invalid",
                "Coarse module unload state does not permit use.",
                disposition="not_attempted",
                kernel=self,
            )


def compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcFgmresFixedRankCoarseKernelV1:
    """Compile, load, bind, and identify the package-owned four-symbol source."""

    try:
        frame = _KERNEL_HANDOFF_V1.get()
        handoff = None if frame is None else frame.claim()
        direct_handoff = handoff is None
        if handoff is None:
            handoff = _HipRtcFgmresFixedRankCoarseKernelHandoffV1()
        try:
            return _compile_impl(
                loaded_runtime,
                architecture,
                hiprtc_library,
                _handoff=handoff,
            )
        except BaseException as primary:
            if direct_handoff:
                _recover_direct_compile_handoff_v1(handoff, primary)
            raise
    except HipRtcFgmresFixedRankCoarseV1Error:
        raise
    except HipRtcError as exc:
        raise HipRtcFgmresFixedRankCoarseV1Error(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_unexpected_failure",
            f"Unexpected coarse HIPRTC failure: {type(exc).__name__}.",
        ) from exc


def _recover_direct_compile_handoff_v1(
    handoff: _HipRtcFgmresFixedRankCoarseKernelHandoffV1,
    primary: BaseException,
) -> None:
    """Close a published owner when a direct compiler call is interrupted."""

    kernel = handoff.kernel
    if kernel is None or kernel.closed:
        return
    try:
        kernel.close()
    except BaseException as cleanup:
        if not isinstance(cleanup, Exception):
            raise
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_compile_cleanup_failed",
            "Published coarse kernel cleanup failed after "
            f"{type(primary).__name__}: {type(cleanup).__name__}.",
        ) from primary


def _compile_fixed_rank_coarse_with_handoff_v1(
    compiler: Any,
    handoff: _HipRtcFgmresFixedRankCoarseKernelHandoffV1,
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcFgmresFixedRankCoarseKernelV1:
    """Call the public compiler under an isolated one-shot cleanup route."""

    if (
        not callable(compiler)
        or type(handoff) is not _HipRtcFgmresFixedRankCoarseKernelHandoffV1
        or handoff.occupied
    ):
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_kernel_handoff_invalid",
            "An exact empty coarse kernel handoff is required.",
        )
    frame = _HipRtcFgmresFixedRankCoarseKernelHandoffFrameV1(handoff)
    isolated_context = copy_context()

    def invoke() -> HipRtcFgmresFixedRankCoarseKernelV1:
        _KERNEL_HANDOFF_V1.set(frame)
        return compiler(loaded_runtime, architecture, hiprtc_library)

    try:
        return isolated_context.run(invoke)
    finally:
        frame.disarm()


def _compile_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
    *,
    _handoff: _HipRtcFgmresFixedRankCoarseKernelHandoffV1,
) -> HipRtcFgmresFixedRankCoarseKernelV1:
    if (
        type(_handoff) is not _HipRtcFgmresFixedRankCoarseKernelHandoffV1
        or _handoff.occupied
    ):
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_kernel_handoff_invalid",
            "An exact empty coarse kernel handoff is required.",
        )
    checked_architecture = _validate_architecture(architecture)
    runtime_identity = _runtime_library_identity(loaded_runtime)
    source = _fixed_source()
    source_hash = _sha256_bytes(source)
    options = (f"--offload-arch={checked_architecture}", *_FIXED_OPTION_SUFFIX)
    rtc = _load_hiprtc_api(hiprtc_library)
    status, rtc_major, rtc_minor = rtc.version()
    if status != 0 or rtc_major < 0 or rtc_minor < 0:
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_runtime_init_failed",
            "hipInit failed: " + _runtime_error_string(loaded_runtime, init_status),
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
        if module.value:
            runtime.unload(module)
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_module_load_failed",
            "hipModuleLoadData failed: " + runtime.error_string(status),
            compile_log=compile_log,
        )
    try:
        functions: dict[str, ctypes.c_void_p] = {}
        for symbol in HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1:
            status, function = runtime.get_function(module, symbol)
            if status != 0 or not function.value:
                raise HipRtcFgmresFixedRankCoarseV1Error(
                    "hip_rtc_fgmres_coarse_symbol_missing",
                    f"Fixed symbol {symbol} is unavailable: "
                    + runtime.error_string(status),
                    compile_log=compile_log,
                )
            functions[symbol] = function
        identity = _build_identity(
            architecture=checked_architecture,
            source_hash=source_hash,
            options=options,
            rtc_version=(rtc_major, rtc_minor),
            rtc_library=rtc.identity,
            runtime_library=runtime_identity,
            code_object=code_object,
        )
        kernel = HipRtcFgmresFixedRankCoarseKernelV1(
            runtime=runtime,
            module=module,
            functions=functions,
            identity=identity,
            _mint=_KERNEL_MINT,
        )
        _handoff.publish(kernel)
        return kernel
    except BaseException:
        if "kernel" in locals() and _handoff.kernel is kernel:
            raise
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
) -> HipRtcFgmresFixedRankCoarseKernelIdentityV1:
    draft = HipRtcFgmresFixedRankCoarseKernelIdentityV1(
        schema_version=(HIP_RTC_FGMRES_FIXED_RANK_COARSE_IDENTITY_SCHEMA_VERSION_V1),
        abi_version=HIP_RTC_FGMRES_FIXED_RANK_COARSE_ABI_VERSION_V1,
        application_abi_version=(
            HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1
        ),
        kernel_name=HIP_RTC_FGMRES_FIXED_RANK_COARSE_KERNEL_NAME_V1,
        prepare_symbol=HIP_FGMRES_FIXED_RANK_COARSE_PREPARE_SYMBOL_V1,
        dot_symbol=HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
        solve_symbol=HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
        apply_symbol=HIP_FGMRES_FIXED_RANK_COARSE_APPLY_SYMBOL_V1,
        vector_block_size=HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
        maximum_rank=16,
        kernel_abi_hash=canonical_hash(
            hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1()
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
    return validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1(identity)


def validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1(
    identity: HipRtcFgmresFixedRankCoarseKernelIdentityV1,
) -> HipRtcFgmresFixedRankCoarseKernelIdentityV1:
    if type(identity) is not HipRtcFgmresFixedRankCoarseKernelIdentityV1:
        _fail(
            "hip_rtc_fgmres_coarse_identity_type_invalid", "Identity type is invalid."
        )
    if (
        identity.schema_version
        != HIP_RTC_FGMRES_FIXED_RANK_COARSE_IDENTITY_SCHEMA_VERSION_V1
        or identity.abi_version != HIP_RTC_FGMRES_FIXED_RANK_COARSE_ABI_VERSION_V1
        or identity.application_abi_version
        != HIP_FGMRES_FIXED_RANK_COARSE_APPLICATION_ABI_VERSION_V1
        or identity.kernel_name != HIP_RTC_FGMRES_FIXED_RANK_COARSE_KERNEL_NAME_V1
        or identity.kernel_symbols != HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1
        or identity.vector_block_size != HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1
        or identity.maximum_rank != 16
        or identity.kernel_abi_hash
        != canonical_hash(hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1())
        or identity.source_resource != _SOURCE_RESOURCE
        or identity.source_sha256 != _sha256_bytes(_fixed_source())
        or identity.compile_options
        != (f"--offload-arch={identity.architecture}", *_FIXED_OPTION_SUFFIX)
        or type(identity.code_object_byte_length) is not int
        or identity.code_object_byte_length <= 0
        or type(identity.hiprtc_version_major) is not int
        or identity.hiprtc_version_major < 0
        or type(identity.hiprtc_version_minor) is not int
        or identity.hiprtc_version_minor < 0
    ):
        _fail(
            "hip_rtc_fgmres_coarse_identity_invalid",
            "Fixed coarse identity fields are invalid.",
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_identity_invalid",
            exc.message,
        ) from exc
    hashes = (
        identity.kernel_abi_hash,
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        _fail(
            "hip_rtc_fgmres_coarse_identity_invalid",
            "Identity hashes are invalid.",
        )
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        _fail(
            "hip_rtc_fgmres_coarse_identity_hash_invalid",
            "Identity hash is invalid.",
        )
    return identity


def _identity_payload(
    identity: HipRtcFgmresFixedRankCoarseKernelIdentityV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "application_abi_version": identity.application_abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": {
            "prepare": identity.prepare_symbol,
            "dot": identity.dot_symbol,
            "solve": identity.solve_symbol,
            "apply": identity.apply_symbol,
        },
        "vector_block_size": identity.vector_block_size,
        "maximum_rank": identity.maximum_rank,
        "kernel_abi_hash": identity.kernel_abi_hash,
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
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_source_missing",
            f"Package source is unavailable: {type(exc).__name__}.",
        ) from exc
    if not source or any(
        source.count(symbol.encode("ascii")) != 1
        for symbol in HIP_FGMRES_FIXED_RANK_COARSE_KERNEL_SYMBOLS_V1
    ):
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_source_invalid",
            "Package source must contain all four fixed symbols exactly once.",
        )
    return source


def _dimensions(
    free_dof_count: Any,
    retained_rank: Any,
    restart_dimension: Any,
    logical_index: Any,
) -> tuple[int, int, int, int]:
    f = _bounded_int(free_dof_count, "free_dof_count", 1, _INT32_MAX)
    k = _bounded_int(retained_rank, "retained_rank", 1, 16)
    m = _bounded_int(
        restart_dimension,
        "restart_dimension",
        1,
        HIP_FGMRES_MAX_RESTART_DIMENSION,
    )
    logical = _bounded_int(logical_index, "logical_index", 0, m - 1)
    return f, k, m, logical


def _bounded_int(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        _fail(
            "hip_rtc_fgmres_coarse_launch_contract_invalid",
            f"{label} must be in [{lower}, {upper}].",
            disposition="not_attempted",
        )
    return value


def _pointer_arguments(values: tuple[tuple[str, Any], ...]) -> tuple[int, ...]:
    return tuple(_runtime_pointer(value, label) for label, value in values)


def _buffer_pointer_arguments(
    values: tuple[tuple[str, Any, int, int], ...],
) -> tuple[int, ...]:
    ranges: list[tuple[int, int, str]] = []
    pointers: list[int] = []
    for label, value, byte_length, alignment in values:
        pointer = _runtime_pointer(value, label)
        if pointer % alignment != 0:
            _fail(
                "hip_rtc_fgmres_coarse_launch_contract_invalid",
                f"{label} must be aligned to {alignment} bytes.",
                disposition="not_attempted",
            )
        if byte_length <= 0 or byte_length - 1 > _UINTPTR_MAX - pointer:
            _fail(
                "hip_rtc_fgmres_coarse_launch_contract_invalid",
                f"{label} byte range does not fit uintptr.",
                disposition="not_attempted",
            )
        pointers.append(pointer)
        ranges.append((pointer, pointer + byte_length, label))
    ordered = sorted(ranges)
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current[0] < previous[1]:
            _fail(
                "hip_rtc_fgmres_coarse_alias_invalid",
                f"{previous[2]} and {current[2]} device ranges overlap.",
                disposition="not_attempted",
            )
    return tuple(pointers)


def _runtime_pointer(value: Any, label: str) -> int:
    try:
        pointer = _pointer_integer(value, label)
    except HipRtcError as exc:
        raise HipRtcFgmresFixedRankCoarseV1Error(
            "hip_rtc_fgmres_coarse_launch_contract_invalid",
            exc.message,
            launch_disposition="not_attempted",
        ) from exc
    if pointer > _UINTPTR_MAX or ctypes.c_void_p(pointer).value != pointer:
        _fail(
            "hip_rtc_fgmres_coarse_launch_contract_invalid",
            f"{label} does not fit uintptr.",
            disposition="not_attempted",
        )
    return pointer


def _fail(
    code: str,
    message: str,
    *,
    disposition: str | None = None,
    kernel: HipRtcFgmresFixedRankCoarseKernelV1 | None = None,
) -> None:
    raise HipRtcFgmresFixedRankCoarseV1Error(
        code,
        message,
        launch_disposition=disposition,
        attempted_launch_count=(
            None if kernel is None else kernel.lifetime_attempted_launch_count
        ),
        accepted_launch_count=(
            None if kernel is None else kernel.lifetime_accepted_launch_count
        ),
    )


__all__ = [
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_ABI_VERSION_V1",
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_IDENTITY_SCHEMA_VERSION_V1",
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_KERNEL_NAME_V1",
    "HipRtcFgmresFixedRankCoarseKernelIdentityV1",
    "HipRtcFgmresFixedRankCoarseKernelV1",
    "HipRtcFgmresFixedRankCoarseV1Error",
    "compile_hip_rtc_fgmres_fixed_rank_coarse_kernel_v1",
    "validate_hip_rtc_fgmres_fixed_rank_coarse_identity_v1",
]
