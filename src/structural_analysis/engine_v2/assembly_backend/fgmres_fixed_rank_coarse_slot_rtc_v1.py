"""HIPRTC owner for one typed fixed-rank coarse recurrence slot.

The module is compiled from the frozen recurrence-v2 source, the frozen
coarse-v1 source, and the slot supplement.  One application submits exactly
four same-stream kernels while retaining precise partial/ambiguous launch
ownership until an external recurrence fence is acknowledged.

This owner does not reserve the recurrence checkpoint ledger and does not by
itself attach coarse status to a terminal solve record.  Those responsibilities
belong to the live typed-slot integration layer.
"""

from __future__ import annotations

import ctypes
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, replace
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
    _runtime_error_string,
    _runtime_library_identity,
    _sha256_bytes,
    _validate_architecture,
    _validate_rtc_library_identity,
    _validate_runtime_identity,
    _valid_sha256,
)

from .fgmres_fixed_rank_coarse_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_BLOCK_SIZE_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
)
from .fgmres_fixed_rank_coarse_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseV1Error,
    _buffer_pointer_arguments,
    _dimensions,
    _runtime_pointer,
)
from .fgmres_fixed_rank_coarse_slot_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLICATION_ABI_VERSION_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLY_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_COMPILE_OPTIONS_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_GATE_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1,
    hip_fgmres_fixed_rank_coarse_slot_kernel_abi_hash_v1,
    hip_fgmres_fixed_rank_coarse_slot_source_components_v1,
    hip_fgmres_fixed_rank_coarse_slot_source_v1,
)
from .fgmres_plan import HIP_FGMRES_MAX_ITERATIONS
from .fgmres_recurrence_plan_v2 import HIP_FGMRES_CONTROL_STATE_BYTES_V2
from .fgmres_rtc_v2 import solve_record_byte_length_v2


HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_IDENTITY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-rtc-fgmres-fixed-rank-coarse-slot-identity.v1"
)
HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_ABI_VERSION_V1 = 1
HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_NAME_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_slot_v1"
)

_INT32_MAX = (1 << 31) - 1
_FP64_BYTES = 8
_U32_BYTES = 4
_KERNEL_MINT = object()


class _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1:
    """One-shot strong owner for an internally compiled slot kernel."""

    __slots__ = ("_kernel", "_lock", "_publication_state", "__weakref__")

    def __init__(self) -> None:
        self._kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1 | None = None
        self._lock = threading.RLock()
        self._publication_state = "empty"

    @property
    def kernel(self) -> HipRtcFgmresFixedRankCoarseSlotKernelV1 | None:
        with self._lock:
            if self._publication_state != "published":
                return None
            return self._kernel

    @property
    def occupied(self) -> bool:
        with self._lock:
            return self._publication_state != "empty"

    def publish(self, kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1) -> None:
        with self._lock:
            if (
                self._publication_state != "empty"
                or self._kernel is not None
                or type(kernel) is not HipRtcFgmresFixedRankCoarseSlotKernelV1
                or kernel.closed
            ):
                raise HipRtcFgmresFixedRankCoarseSlotV1Error(
                    "hip_rtc_fgmres_coarse_slot_kernel_handoff_invalid",
                    "The handoff accepts one exact live typed-slot kernel.",
                )
            self._publication_state = "reserved"
            try:
                self._kernel = kernel
                self._publication_state = "published"
            except BaseException:
                self._publication_state = "spent"
                raise


class _HipRtcFgmresFixedRankCoarseSlotKernelHandoffFrameV1:
    """One-shot weak task-local route that owns no native resource."""

    __slots__ = ("_target_refs",)

    def __init__(
        self,
        target: _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1,
    ) -> None:
        self._target_refs = [weakref.ref(target)]

    def claim(self) -> _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1 | None:
        try:
            target_ref = self._target_refs.pop()
        except IndexError:
            return None
        return target_ref()

    def disarm(self) -> None:
        self._target_refs.clear()


_SLOT_KERNEL_HANDOFF_V1: ContextVar[
    _HipRtcFgmresFixedRankCoarseSlotKernelHandoffFrameV1 | None
] = ContextVar(
    "engine_v2_fgmres_fixed_rank_coarse_slot_kernel_handoff_v1",
    default=None,
)


class HipRtcFgmresFixedRankCoarseSlotV1Error(HipRtcError):
    """Stable typed-slot error retaining native acceptance information."""

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
class HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1:
    schema_version: str
    abi_version: int
    application_abi_version: int
    kernel_name: str
    kernel_symbols: tuple[str, str, str, str]
    kernel_abi_hash: str
    recurrence_source_sha256: str
    coarse_source_sha256: str
    slot_source_sha256: str
    combined_source_sha256: str
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
        validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(self)
        return _identity_payload(self, include_hash=True)


class HipRtcFgmresFixedRankCoarseSlotKernelV1:
    """Loaded four-symbol typed-slot module with exact fence ownership."""

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
        runtime: Any,
        module: ctypes.c_void_p,
        functions: dict[str, ctypes.c_void_p],
        identity: HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1,
        _mint: object | None = None,
    ) -> None:
        if _mint is not _KERNEL_MINT:
            raise TypeError("typed coarse-slot kernels are compiler issued only")
        if tuple(functions) != HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1:
            raise HipRtcFgmresFixedRankCoarseSlotV1Error(
                "hip_rtc_fgmres_coarse_slot_binding_invalid",
                "The exact typed-slot four-symbol binding set is required.",
            )
        validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(identity)
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
    def identity(self) -> HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1:
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

    def launch_slot(
        self,
        *,
        stream: Any,
        expected_schedule_epoch: int,
        expected_restart: int,
        expected_column: int,
        maximum_restart_count: int,
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
        control_state: Any,
        solve_record: Any,
    ) -> int:
        """Enqueue one logical coarse slot as exactly four physical kernels."""

        with self._serialized_operation("/launch_slot"):
            self._require_open()
            schedule_epoch = _bounded_int(
                expected_schedule_epoch,
                "expected_schedule_epoch",
                0,
                _INT32_MAX,
            )
            restart = _bounded_int(
                expected_restart,
                "expected_restart",
                1,
                HIP_FGMRES_MAX_ITERATIONS,
            )
            f, k, m, logical = _coarse_dimensions(
                free_dof_count,
                retained_rank,
                restart_dimension,
                logical_index,
            )
            column = _bounded_int(
                expected_column,
                "expected_column",
                0,
                m - 1,
            )
            restarts = _bounded_int(
                maximum_restart_count,
                "maximum_restart_count",
                1,
                HIP_FGMRES_MAX_ITERATIONS,
            )
            if restart > restarts or logical != column:
                _fail(
                    "hip_rtc_fgmres_coarse_slot_coordinate_invalid",
                    "Typed-slot recurrence coordinates are inconsistent.",
                    disposition="not_attempted",
                    kernel=self,
                )
            pointers = _slot_pointer_arguments(
                f=f,
                k=k,
                m=m,
                maximum_restart_count=restarts,
                values=(
                    jacobi_inverse,
                    basis_v,
                    preconditioned_basis_z,
                    coarse_physical_basis_z,
                    coarse_operator_basis_az,
                    coarse_cholesky_l,
                    coarse_rhs,
                    coarse_coefficients,
                    coarse_status,
                    control_state,
                    solve_record,
                ),
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
                control_pointer,
                solve_record_pointer,
            ) = pointers
            accepted_before = self._lifetime_accepted_launch_count
            common_scalars = (f, k, m, logical)
            self._launch(
                HIP_FGMRES_FIXED_RANK_COARSE_SLOT_GATE_SYMBOL_V1,
                stream=stream,
                grid_x=1,
                block_x=1,
                scalar_values=(schedule_epoch, restart, column, *common_scalars),
                pointer_values=(
                    rhs_pointer,
                    coefficients_pointer,
                    status_pointer,
                    control_pointer,
                    solve_record_pointer,
                ),
                operation="coarse slot gate",
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
                operation="coarse slot dot",
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
                operation="coarse slot Cholesky solve",
            )
            self._launch(
                HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLY_SYMBOL_V1,
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
                operation="coarse slot apply",
            )
            accepted = self._lifetime_accepted_launch_count - accepted_before
            if accepted != 4:
                _fail(
                    "hip_rtc_fgmres_coarse_slot_launch_count_invalid",
                    "One typed slot must accept exactly four launches.",
                    disposition="ambiguous",
                    kernel=self,
                )
            return accepted

    def acknowledge_stream_fence(self, stream: Any) -> int:
        """Release pending slot work after the exact stream is fenced."""

        with self._serialized_operation("/fence"):
            self._require_open()
            stream_pointer = _runtime_pointer(stream, "stream")
            if self._pending_stream_pointer not in {None, stream_pointer}:
                _fail(
                    "hip_rtc_fgmres_coarse_slot_fence_stream_invalid",
                    "Fence stream does not match the typed-slot launch stream.",
                    disposition="not_attempted",
                    kernel=self,
                )
            accepted = self._pending_accepted_launch_count
            self._pending_stream_pointer = None
            self._pending_accepted_launch_count = 0
            self._pending_uncertain = False
            return accepted

    def close(self) -> None:
        """Unload only after every accepted or uncertain launch is fenced."""

        with self._serialized_operation("/close"):
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
                    "hip_rtc_fgmres_coarse_slot_module_unload_uncertain",
                    "The typed-slot module unload outcome is uncertain and cannot "
                    "be retried.",
                    disposition="not_attempted",
                    kernel=self,
                )
            if self.pending:
                _fail(
                    "hip_rtc_fgmres_coarse_slot_pending_work",
                    "The typed-slot module cannot unload before a fence.",
                    disposition="not_attempted",
                    kernel=self,
                )
            status: int | None = None
            self._unload_disposition = "unload_call_inflight"
            try:
                status = int(self._runtime.unload(self._module))
                self._unload_disposition = (
                    "external_unload_succeeded" if status == 0 else "live"
                )
            except BaseException as exc:
                self._unload_disposition = (
                    "external_unload_succeeded"
                    if status == 0
                    else ("live" if status is not None else "unload_outcome_uncertain")
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipRtcFgmresFixedRankCoarseSlotV1Error(
                    "hip_rtc_fgmres_coarse_slot_module_unload_uncertain",
                    "hipModuleUnload raised "
                    f"{type(exc).__name__}; outcome is uncertain.",
                ) from exc
            if status != 0:
                raise HipRtcFgmresFixedRankCoarseSlotV1Error(
                    "hip_rtc_fgmres_coarse_slot_module_unload_failed",
                    "hipModuleUnload failed: " + self._runtime.error_string(status),
                )
            self._finish_close()

    def _finish_close(self) -> None:
        if self._unload_disposition != "external_unload_succeeded":
            raise RuntimeError("typed-slot module close finalization is not authorized")
        self._module = ctypes.c_void_p()
        self._functions = {}
        self._unload_disposition = "terminal"
        self._closed = True

    def _serialized_operation(self, path: str) -> _SerializedSlotOperation:
        return _SerializedSlotOperation(self, path)

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
                "hip_rtc_fgmres_coarse_slot_stream_changed",
                "All typed-slot launches must use one stream until fenced.",
                disposition="not_attempted",
                kernel=self,
            )
        function = self._functions.get(symbol)
        if type(function) is not ctypes.c_void_p or not function.value:
            _fail(
                "hip_rtc_fgmres_coarse_slot_binding_changed",
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
        previous_stream = self._pending_stream_pointer
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
            raise HipRtcFgmresFixedRankCoarseSlotV1Error(
                "hip_rtc_fgmres_coarse_slot_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
                launch_disposition="ambiguous",
                attempted_launch_count=self._lifetime_attempted_launch_count,
                accepted_launch_count=self._lifetime_accepted_launch_count,
            ) from exc
        if status != 0:
            self._pending_stream_pointer = previous_stream
            self._pending_uncertain = previous_uncertain
            raise HipRtcFgmresFixedRankCoarseSlotV1Error(
                "hip_rtc_fgmres_coarse_slot_kernel_launch_failed",
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
                "hip_rtc_fgmres_coarse_slot_kernel_closed",
                "Typed-slot kernel is closed.",
                disposition="not_attempted",
                kernel=self,
            )
        if self._unload_disposition != "live":
            _fail(
                "hip_rtc_fgmres_coarse_slot_module_state_invalid",
                "Typed-slot module unload state does not permit use.",
                disposition="not_attempted",
                kernel=self,
            )


class _SerializedSlotOperation:
    __slots__ = ("_kernel", "_path")

    def __init__(
        self,
        kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1,
        path: str,
    ) -> None:
        self._kernel = kernel
        self._path = path

    def __enter__(self) -> None:
        kernel = self._kernel
        kernel._operation_lock.acquire()
        if kernel._operation_active:
            kernel._operation_lock.release()
            _fail(
                "hip_rtc_fgmres_coarse_slot_reentrant_operation",
                f"Reentrant typed-slot operation at {self._path}.",
                disposition="not_attempted",
                kernel=kernel,
            )
        kernel._operation_active = True

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        kernel = self._kernel
        kernel._operation_active = False
        kernel._operation_lock.release()


def compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
    """Compile, load, bind, and identify the package-owned typed-slot source."""

    try:
        frame = _SLOT_KERNEL_HANDOFF_V1.get()
        handoff = None if frame is None else frame.claim()
        direct_handoff = handoff is None
        if handoff is None:
            handoff = _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1()
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
    except HipRtcFgmresFixedRankCoarseSlotV1Error:
        raise
    except HipRtcError as exc:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_unexpected_failure",
            f"Unexpected typed-slot HIPRTC failure: {type(exc).__name__}.",
        ) from exc


def _recover_direct_compile_handoff_v1(
    handoff: _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1,
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
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_compile_cleanup_failed",
            "Published typed-slot kernel cleanup failed after "
            f"{type(primary).__name__}: {type(cleanup).__name__}.",
        ) from primary


def _compile_fixed_rank_coarse_slot_with_handoff_v1(
    compiler: Any,
    handoff: _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1,
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
    """Call the public compiler under an isolated one-shot cleanup route."""

    if (
        not callable(compiler)
        or type(handoff) is not _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1
        or handoff.occupied
    ):
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_kernel_handoff_invalid",
            "An exact empty typed-slot kernel handoff is required.",
        )
    frame = _HipRtcFgmresFixedRankCoarseSlotKernelHandoffFrameV1(handoff)
    isolated_context = copy_context()

    def invoke() -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
        _SLOT_KERNEL_HANDOFF_V1.set(frame)
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
    _handoff: _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1,
) -> HipRtcFgmresFixedRankCoarseSlotKernelV1:
    if (
        type(_handoff) is not _HipRtcFgmresFixedRankCoarseSlotKernelHandoffV1
        or _handoff.occupied
    ):
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_kernel_handoff_invalid",
            "An exact empty typed-slot kernel handoff is required.",
        )
    checked_architecture = _validate_architecture(architecture)
    runtime_identity = _runtime_library_identity(loaded_runtime)
    source = hip_fgmres_fixed_rank_coarse_slot_source_v1()
    source_hash = _sha256_bytes(source)
    options = (
        f"--offload-arch={checked_architecture}",
        *HIP_FGMRES_FIXED_RANK_COARSE_SLOT_COMPILE_OPTIONS_V1,
    )
    rtc = _load_hiprtc_api(hiprtc_library)
    status, rtc_major, rtc_minor = rtc.version()
    if status != 0 or rtc_major < 0 or rtc_minor < 0:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_runtime_init_failed",
            "hipInit failed: " + _runtime_error_string(loaded_runtime, init_status),
        )
    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(
        rtc,
        source,
        options,
        program_name=Path(slot_module_resource()).name,
    )
    status, module = runtime.load_module(code_object)
    if status != 0 or not module.value:
        if module.value:
            runtime.unload(module)
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_module_load_failed",
            "hipModuleLoadData failed: " + runtime.error_string(status),
            compile_log=compile_log,
        )
    try:
        functions: dict[str, ctypes.c_void_p] = {}
        for symbol in HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1:
            status, function = runtime.get_function(module, symbol)
            if status != 0 or not function.value:
                raise HipRtcFgmresFixedRankCoarseSlotV1Error(
                    "hip_rtc_fgmres_coarse_slot_symbol_missing",
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
        kernel = HipRtcFgmresFixedRankCoarseSlotKernelV1(
            runtime=runtime,
            module=module,
            functions=functions,
            identity=identity,
            _mint=_KERNEL_MINT,
        )
        _handoff.publish(kernel)
        return kernel
    except BaseException as primary:
        if "kernel" in locals() and _handoff.kernel is kernel:
            raise
        _cleanup_unpublished_module(runtime, module, primary)
        raise


def _cleanup_unpublished_module(
    runtime: _RuntimeModuleApi,
    module: ctypes.c_void_p,
    primary: BaseException,
) -> None:
    """Release a loaded module whose typed owner was never published."""

    try:
        status = int(runtime.unload(module))
    except BaseException as cleanup:
        if not isinstance(cleanup, Exception):
            raise
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_compile_cleanup_uncertain",
            "Unpublished typed-slot module cleanup raised "
            f"{type(cleanup).__name__} after {type(primary).__name__}.",
        ) from primary
    if status != 0:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_compile_cleanup_failed",
            "Unpublished typed-slot module cleanup failed after "
            f"{type(primary).__name__}: {runtime.error_string(status)}.",
        ) from primary


def slot_module_resource() -> str:
    return "kernels/engine_v2_fgmres_fixed_rank_coarse_slot_v1.hip.cpp"


def _build_identity(
    *,
    architecture: str,
    source_hash: str,
    options: tuple[str, ...],
    rtc_version: tuple[int, int],
    rtc_library: HipRtcLibraryIdentity,
    runtime_library: HipRuntimeLibraryIdentity,
    code_object: bytes,
) -> HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1:
    components = hip_fgmres_fixed_rank_coarse_slot_source_components_v1()
    draft = HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1(
        schema_version=(
            HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_IDENTITY_SCHEMA_VERSION_V1
        ),
        abi_version=HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_ABI_VERSION_V1,
        application_abi_version=(
            HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLICATION_ABI_VERSION_V1
        ),
        kernel_name=HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_NAME_V1,
        kernel_symbols=HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1,
        kernel_abi_hash=hip_fgmres_fixed_rank_coarse_slot_kernel_abi_hash_v1(),
        recurrence_source_sha256=components["recurrence"]["sha256"],
        coarse_source_sha256=components["coarse"]["sha256"],
        slot_source_sha256=components["slot"]["sha256"],
        combined_source_sha256=source_hash,
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
    return validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(identity)


def validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1(
    identity: HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1,
) -> HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1:
    if type(identity) is not HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1:
        _fail("hip_rtc_fgmres_coarse_slot_identity_type_invalid", "Invalid type.")
    components = hip_fgmres_fixed_rank_coarse_slot_source_components_v1()
    if (
        identity.schema_version
        != HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_IDENTITY_SCHEMA_VERSION_V1
        or identity.abi_version != HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_ABI_VERSION_V1
        or identity.application_abi_version
        != HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLICATION_ABI_VERSION_V1
        or identity.kernel_name != HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_NAME_V1
        or identity.kernel_symbols
        != HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1
        or identity.kernel_abi_hash
        != hip_fgmres_fixed_rank_coarse_slot_kernel_abi_hash_v1()
        or identity.recurrence_source_sha256 != components["recurrence"]["sha256"]
        or identity.coarse_source_sha256 != components["coarse"]["sha256"]
        or identity.slot_source_sha256 != components["slot"]["sha256"]
        or identity.combined_source_sha256 != components["combined"]["sha256"]
        or identity.compile_options
        != (
            f"--offload-arch={identity.architecture}",
            *HIP_FGMRES_FIXED_RANK_COARSE_SLOT_COMPILE_OPTIONS_V1,
        )
        or type(identity.hiprtc_version_major) is not int
        or identity.hiprtc_version_major < 0
        or type(identity.hiprtc_version_minor) is not int
        or identity.hiprtc_version_minor < 0
        or type(identity.code_object_byte_length) is not int
        or identity.code_object_byte_length <= 0
    ):
        _fail(
            "hip_rtc_fgmres_coarse_slot_identity_invalid",
            "Typed-slot kernel identity fields are inconsistent.",
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_identity_invalid",
            exc.message,
        ) from exc
    hashes = (
        identity.kernel_abi_hash,
        identity.recurrence_source_sha256,
        identity.coarse_source_sha256,
        identity.slot_source_sha256,
        identity.combined_source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        _fail(
            "hip_rtc_fgmres_coarse_slot_identity_invalid",
            "Typed-slot kernel identity hashes are invalid.",
        )
    try:
        expected_hash = canonical_hash(_identity_payload(identity, include_hash=False))
    except Exception as exc:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_identity_invalid",
            f"Typed-slot identity serialization failed: {type(exc).__name__}.",
        ) from exc
    if identity.identity_hash != expected_hash:
        _fail(
            "hip_rtc_fgmres_coarse_slot_identity_invalid",
            "Typed-slot kernel identity is inconsistent.",
        )
    return identity


def _identity_payload(
    identity: HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "application_abi_version": identity.application_abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": list(identity.kernel_symbols),
        "kernel_abi_hash": identity.kernel_abi_hash,
        "recurrence_source_sha256": identity.recurrence_source_sha256,
        "coarse_source_sha256": identity.coarse_source_sha256,
        "slot_source_sha256": identity.slot_source_sha256,
        "combined_source_sha256": identity.combined_source_sha256,
        "compile_options": list(identity.compile_options),
        "architecture": identity.architecture,
        "hiprtc_version": [
            identity.hiprtc_version_major,
            identity.hiprtc_version_minor,
        ],
        "hiprtc_library": identity.hiprtc_library.to_dict(),
        "runtime_library": identity.runtime_library.to_dict(),
        "code_object_byte_length": identity.code_object_byte_length,
        "code_object_sha256": identity.code_object_sha256,
    }
    if include_hash:
        payload["identity_hash"] = identity.identity_hash
    return payload


def _coarse_dimensions(
    free_dof_count: Any,
    retained_rank: Any,
    restart_dimension: Any,
    logical_index: Any,
) -> tuple[int, int, int, int]:
    try:
        return _dimensions(
            free_dof_count,
            retained_rank,
            restart_dimension,
            logical_index,
        )
    except HipRtcFgmresFixedRankCoarseV1Error as exc:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_launch_contract_invalid",
            exc.message,
            launch_disposition="not_attempted",
        ) from exc


def _slot_pointer_arguments(
    *,
    f: int,
    k: int,
    m: int,
    maximum_restart_count: int,
    values: tuple[Any, ...],
) -> tuple[int, ...]:
    (
        jacobi_inverse,
        basis_v,
        preconditioned_basis_z,
        coarse_physical_basis_z,
        coarse_operator_basis_az,
        coarse_cholesky_l,
        coarse_rhs,
        coarse_coefficients,
        coarse_status,
        control_state,
        solve_record,
    ) = values
    try:
        return _buffer_pointer_arguments(
            (
                ("jacobi_inverse", jacobi_inverse, f * _FP64_BYTES, _FP64_BYTES),
                (
                    "basis_v",
                    basis_v,
                    (m + 1) * f * _FP64_BYTES,
                    _FP64_BYTES,
                ),
                (
                    "preconditioned_basis_z",
                    preconditioned_basis_z,
                    m * f * _FP64_BYTES,
                    _FP64_BYTES,
                ),
                (
                    "coarse_physical_basis_z",
                    coarse_physical_basis_z,
                    f * k * _FP64_BYTES,
                    _FP64_BYTES,
                ),
                (
                    "coarse_operator_basis_az",
                    coarse_operator_basis_az,
                    f * k * _FP64_BYTES,
                    _FP64_BYTES,
                ),
                (
                    "coarse_cholesky_l",
                    coarse_cholesky_l,
                    k * k * _FP64_BYTES,
                    _FP64_BYTES,
                ),
                ("coarse_rhs", coarse_rhs, k * _FP64_BYTES, _FP64_BYTES),
                (
                    "coarse_coefficients",
                    coarse_coefficients,
                    k * _FP64_BYTES,
                    _FP64_BYTES,
                ),
                ("coarse_status", coarse_status, _U32_BYTES, _U32_BYTES),
                (
                    "control_state",
                    control_state,
                    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
                    _FP64_BYTES,
                ),
                (
                    "solve_record",
                    solve_record,
                    solve_record_byte_length_v2(maximum_restart_count),
                    _FP64_BYTES,
                ),
            )
        )
    except HipRtcFgmresFixedRankCoarseV1Error as exc:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_pointer_contract_invalid",
            exc.message,
            launch_disposition="not_attempted",
        ) from exc


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise HipRtcFgmresFixedRankCoarseSlotV1Error(
            "hip_rtc_fgmres_coarse_slot_launch_contract_invalid",
            f"{label} must be an exact int in [{minimum}, {maximum}].",
            launch_disposition="not_attempted",
        )
    return value


def _fail(
    code: str,
    message: str,
    *,
    disposition: str | None = None,
    kernel: HipRtcFgmresFixedRankCoarseSlotKernelV1 | None = None,
) -> None:
    raise HipRtcFgmresFixedRankCoarseSlotV1Error(
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
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_ABI_VERSION_V1",
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_IDENTITY_SCHEMA_VERSION_V1",
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_NAME_V1",
    "HipRtcFgmresFixedRankCoarseSlotKernelIdentityV1",
    "HipRtcFgmresFixedRankCoarseSlotKernelV1",
    "HipRtcFgmresFixedRankCoarseSlotV1Error",
    "compile_hip_rtc_fgmres_fixed_rank_coarse_slot_kernel_v1",
    "slot_module_resource",
    "validate_hip_rtc_fgmres_fixed_rank_coarse_slot_identity_v1",
]
