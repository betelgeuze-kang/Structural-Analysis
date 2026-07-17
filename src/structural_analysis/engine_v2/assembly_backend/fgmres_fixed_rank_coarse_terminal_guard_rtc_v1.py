"""HIPRTC owner for device-side fixed-rank coarse terminal publication."""

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

from .fgmres_fixed_rank_coarse_rtc_v1 import (
    HipRtcFgmresFixedRankCoarseV1Error,
    _buffer_pointer_arguments,
    _runtime_pointer,
)
from .fgmres_fixed_rank_coarse_terminal_guard_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_ABI_VERSION_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1,
    hip_fgmres_fixed_rank_coarse_terminal_guard_abi_hash_v1,
    hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1,
    hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1,
)
from .fgmres_plan import (
    HIP_FGMRES_MAX_ITERATIONS,
    HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES,
    HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES,
)
from .fgmres_recurrence_plan_v2 import HIP_FGMRES_CONTROL_STATE_BYTES_V2


HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_IDENTITY_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-rtc-fgmres-fixed-rank-coarse-terminal-guard-identity.v1"
)
HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_KERNEL_NAME_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_terminal_guard_v1"
)

_KERNEL_MINT = object()
_U32_BYTES = 4
_FP64_BYTES = 8


class HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(HipRtcError):
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
class HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1:
    schema_version: str
    abi_version: int
    kernel_name: str
    symbol: str
    kernel_abi_hash: str
    recurrence_source_sha256: str
    guard_source_sha256: str
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
        validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1(self)
        return _identity_payload(self, include_hash=True)


class HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
    """One-symbol owner retaining accepted/uncertain work until a fence."""

    __slots__ = (
        "_runtime",
        "_module",
        "_function",
        "_identity",
        "_lock",
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
        function: ctypes.c_void_p,
        identity: HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1,
        _mint: object | None = None,
    ) -> None:
        if _mint is not _KERNEL_MINT:
            raise TypeError("coarse terminal guards are compiler issued only")
        if type(function) is not ctypes.c_void_p or not function.value:
            raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                "hip_rtc_fgmres_coarse_terminal_guard_binding_invalid",
                "The exact terminal-guard symbol binding is required.",
            )
        validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1(identity)
        self._runtime = runtime
        self._module = module
        self._function = function
        self._identity = identity
        self._lock = threading.RLock()
        self._operation_active = False
        self._closed = False
        self._unload_disposition = "live"
        self._pending_stream_pointer: int | None = None
        self._pending_accepted_launch_count = 0
        self._pending_uncertain = False
        self._lifetime_attempted_launch_count = 0
        self._lifetime_accepted_launch_count = 0

    @property
    def identity(self) -> HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1:
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

    def launch_guard(
        self,
        *,
        stream: Any,
        maximum_restart_count: int,
        coarse_status: Any,
        control_state: Any,
        solve_record: Any,
    ) -> None:
        with self._serialized_operation("/launch"):
            self._require_open()
            if self._pending_uncertain:
                self._fail(
                    "hip_rtc_fgmres_coarse_terminal_guard_fence_required",
                    "An uncertain terminal-guard launch must be fenced before "
                    "another launch can be accepted.",
                    "not_attempted",
                )
            restarts = _bounded_int(
                maximum_restart_count,
                "maximum_restart_count",
                1,
                HIP_FGMRES_MAX_ITERATIONS,
            )
            try:
                status_pointer, control_pointer, record_pointer = (
                    _buffer_pointer_arguments(
                        (
                            (
                                "coarse_status",
                                coarse_status,
                                _U32_BYTES,
                                _U32_BYTES,
                            ),
                            (
                                "control_state",
                                control_state,
                                HIP_FGMRES_CONTROL_STATE_BYTES_V2,
                                _FP64_BYTES,
                            ),
                            (
                                "solve_record",
                                solve_record,
                                HIP_FGMRES_SOLVE_RECORD_HEADER_BYTES
                                + HIP_FGMRES_SOLVE_RECORD_RESTART_BYTES * restarts,
                                _FP64_BYTES,
                            ),
                        )
                    )
                )
            except HipRtcFgmresFixedRankCoarseV1Error as exc:
                raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                    "hip_rtc_fgmres_coarse_terminal_guard_pointer_invalid",
                    exc.message,
                    launch_disposition="not_attempted",
                ) from exc
            stream_pointer = _guard_runtime_pointer(stream, "stream")
            if self._pending_stream_pointer not in {None, stream_pointer}:
                self._fail(
                    "hip_rtc_fgmres_coarse_terminal_guard_stream_changed",
                    "All terminal guards must use one stream until fenced.",
                    "not_attempted",
                )
            if type(self._function) is not ctypes.c_void_p or not self._function.value:
                self._fail(
                    "hip_rtc_fgmres_coarse_terminal_guard_binding_changed",
                    "The exact terminal-guard symbol binding is unavailable.",
                    "not_attempted",
                )
            pointer_storage = [
                ctypes.c_void_p(status_pointer),
                ctypes.c_void_p(control_pointer),
                ctypes.c_void_p(record_pointer),
            ]
            parameters = (ctypes.c_void_p * 3)(
                *(
                    ctypes.cast(ctypes.byref(argument), ctypes.c_void_p)
                    for argument in pointer_storage
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
                        self._function,
                        grid_x=1,
                        block_x=1,
                        stream=ctypes.c_void_p(stream_pointer),
                        parameters=parameters,
                    )
                )
            except BaseException as exc:
                if not isinstance(exc, Exception):
                    raise
                raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                    "hip_rtc_fgmres_coarse_terminal_guard_launch_failed",
                    f"hipModuleLaunchKernel raised {type(exc).__name__}.",
                    launch_disposition="ambiguous",
                    attempted_launch_count=self._lifetime_attempted_launch_count,
                    accepted_launch_count=self._lifetime_accepted_launch_count,
                ) from exc
            if status != 0:
                self._pending_stream_pointer = previous_stream
                self._pending_uncertain = previous_uncertain
                raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                    "hip_rtc_fgmres_coarse_terminal_guard_launch_failed",
                    "hipModuleLaunchKernel failed: "
                    f"{self._runtime.error_string(status)}.",
                    launch_disposition="rejected",
                    attempted_launch_count=self._lifetime_attempted_launch_count,
                    accepted_launch_count=self._lifetime_accepted_launch_count,
                )
            self._pending_accepted_launch_count += 1
            self._lifetime_accepted_launch_count += 1
            self._pending_uncertain = previous_uncertain

    def acknowledge_stream_fence(self, stream: Any) -> int:
        with self._serialized_operation("/fence"):
            self._require_open()
            stream_pointer = _guard_runtime_pointer(stream, "stream")
            if self._pending_stream_pointer not in {None, stream_pointer}:
                self._fail(
                    "hip_rtc_fgmres_coarse_terminal_guard_fence_stream_invalid",
                    "Fence stream does not match the terminal-guard stream.",
                    "not_attempted",
                )
            accepted = self._pending_accepted_launch_count
            self._pending_stream_pointer = None
            self._pending_accepted_launch_count = 0
            self._pending_uncertain = False
            return accepted

    def close(self) -> None:
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
                self._fail(
                    "hip_rtc_fgmres_coarse_terminal_guard_unload_uncertain",
                    "The prior module unload outcome is uncertain.",
                    "not_attempted",
                )
            if self.pending:
                self._fail(
                    "hip_rtc_fgmres_coarse_terminal_guard_pending_work",
                    "The terminal-guard module cannot unload before a fence.",
                    "not_attempted",
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
                raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                    "hip_rtc_fgmres_coarse_terminal_guard_unload_uncertain",
                    f"hipModuleUnload raised {type(exc).__name__}.",
                ) from exc
            if status != 0:
                raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                    "hip_rtc_fgmres_coarse_terminal_guard_unload_failed",
                    "hipModuleUnload failed: " + self._runtime.error_string(status),
                )
            self._finish_close()

    def _finish_close(self) -> None:
        if self._unload_disposition != "external_unload_succeeded":
            raise RuntimeError("terminal-guard close finalization is unauthorized")
        self._module = ctypes.c_void_p()
        self._function = ctypes.c_void_p()
        self._unload_disposition = "terminal"
        self._closed = True

    def _serialized_operation(self, path: str) -> _SerializedGuardOperation:
        return _SerializedGuardOperation(self, path)

    def _require_open(self) -> None:
        if self._closed or self._unload_disposition != "live":
            self._fail(
                "hip_rtc_fgmres_coarse_terminal_guard_unavailable",
                "Terminal-guard module state does not permit use.",
                "not_attempted",
            )

    def _fail(self, code: str, message: str, disposition: str | None) -> None:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            code,
            message,
            launch_disposition=disposition,
            attempted_launch_count=self._lifetime_attempted_launch_count,
            accepted_launch_count=self._lifetime_accepted_launch_count,
        )


class _SerializedGuardOperation:
    def __init__(
        self,
        kernel: HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1,
        path: str,
    ) -> None:
        self._kernel = kernel
        self._path = path

    def __enter__(self) -> None:
        self._kernel._lock.acquire()
        if self._kernel._operation_active:
            self._kernel._lock.release()
            self._kernel._fail(
                "hip_rtc_fgmres_coarse_terminal_guard_reentrant_operation",
                f"Reentrant terminal-guard operation at {self._path}.",
                "not_attempted",
            )
        self._kernel._operation_active = True

    def __exit__(self, _type: Any, _value: Any, _traceback: Any) -> None:
        self._kernel._operation_active = False
        self._kernel._lock.release()


class _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1:
    __slots__ = ("_kernel", "_lock", "_state", "__weakref__")

    def __init__(self) -> None:
        self._kernel: HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1 | None = None
        self._lock = threading.RLock()
        self._state = "empty"

    @property
    def kernel(self) -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1 | None:
        with self._lock:
            return self._kernel if self._state == "published" else None

    @property
    def occupied(self) -> bool:
        with self._lock:
            return self._state != "empty"

    def publish(
        self,
        kernel: HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1,
    ) -> None:
        with self._lock:
            if (
                self._state != "empty"
                or self._kernel is not None
                or type(kernel) is not HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1
                or kernel.closed
            ):
                raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                    "hip_rtc_fgmres_coarse_terminal_guard_handoff_invalid",
                    "The handoff accepts one exact live terminal guard.",
                )
            self._state = "reserved"
            try:
                self._kernel = kernel
                self._state = "published"
            except BaseException:
                self._state = "spent"
                raise


class _GuardHandoffFrame:
    __slots__ = ("_refs",)

    def __init__(
        self,
        handoff: _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1,
    ) -> None:
        self._refs = [weakref.ref(handoff)]

    def claim(self) -> _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1 | None:
        try:
            reference = self._refs.pop()
        except IndexError:
            return None
        return reference()

    def disarm(self) -> None:
        self._refs.clear()


_GUARD_HANDOFF: ContextVar[_GuardHandoffFrame | None] = ContextVar(
    "engine_v2_fgmres_fixed_rank_coarse_terminal_guard_handoff_v1",
    default=None,
)


def compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
    try:
        frame = _GUARD_HANDOFF.get()
        handoff = None if frame is None else frame.claim()
        direct = handoff is None
        if handoff is None:
            handoff = _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1()
        try:
            return _compile_impl(
                loaded_runtime,
                architecture,
                hiprtc_library,
                _handoff=handoff,
            )
        except BaseException as primary:
            if direct:
                _recover_handoff(handoff, primary)
            raise
    except HipRtcFgmresFixedRankCoarseTerminalGuardV1Error:
        raise
    except HipRtcError as exc:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_unexpected_failure",
            f"Unexpected terminal-guard HIPRTC failure: {type(exc).__name__}.",
        ) from exc


def _compile_terminal_guard_with_handoff_v1(
    compiler: Any,
    handoff: _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1,
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
    if (
        not callable(compiler)
        or type(handoff) is not (_HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1)
        or handoff.occupied
    ):
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_handoff_invalid",
            "An exact empty terminal-guard handoff is required.",
        )
    frame = _GuardHandoffFrame(handoff)
    context = copy_context()

    def invoke() -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
        _GUARD_HANDOFF.set(frame)
        return compiler(loaded_runtime, architecture, hiprtc_library)

    try:
        return context.run(invoke)
    finally:
        frame.disarm()


def _recover_handoff(
    handoff: _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1,
    primary: BaseException,
) -> None:
    kernel = handoff.kernel
    if kernel is None or kernel.closed:
        return
    try:
        kernel.close()
    except BaseException as cleanup:
        if not isinstance(cleanup, Exception):
            raise
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_compile_cleanup_failed",
            f"Published guard cleanup failed after {type(primary).__name__}: "
            f"{type(cleanup).__name__}.",
        ) from primary


def _compile_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
    *,
    _handoff: _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1,
) -> HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1:
    if type(_handoff) is not _HipRtcFgmresFixedRankCoarseTerminalGuardHandoffV1 or (
        _handoff.occupied
    ):
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_handoff_invalid",
            "An exact empty terminal-guard handoff is required.",
        )
    checked_architecture = _validate_architecture(architecture)
    runtime_identity = _runtime_library_identity(loaded_runtime)
    source = hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1()
    options = (
        f"--offload-arch={checked_architecture}",
        *HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1,
    )
    rtc = _load_hiprtc_api(hiprtc_library)
    status, major, minor = rtc.version()
    if status != 0 or major < 0 or minor < 0:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_runtime_init_failed",
            "hipInit failed: " + _runtime_error_string(loaded_runtime, init_status),
        )
    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(
        rtc,
        source,
        options,
        program_name="engine_v2_fgmres_fixed_rank_coarse_terminal_guard_v1.hip.cpp",
    )
    status, module = runtime.load_module(code_object)
    if status != 0 or not module.value:
        if module.value:
            runtime.unload(module)
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_module_load_failed",
            "hipModuleLoadData failed: " + runtime.error_string(status),
            compile_log=compile_log,
        )
    try:
        status, function = runtime.get_function(
            module,
            HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1,
        )
        if status != 0 or not function.value:
            raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
                "hip_rtc_fgmres_coarse_terminal_guard_symbol_missing",
                "Fixed terminal-guard symbol is unavailable: "
                + runtime.error_string(status),
                compile_log=compile_log,
            )
        identity = _build_identity(
            architecture=checked_architecture,
            options=options,
            rtc_version=(major, minor),
            rtc_library=rtc.identity,
            runtime_library=runtime_identity,
            code_object=code_object,
        )
        kernel = HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1(
            runtime=runtime,
            module=module,
            function=function,
            identity=identity,
            _mint=_KERNEL_MINT,
        )
        _handoff.publish(kernel)
        return kernel
    except BaseException as primary:
        if "kernel" in locals() and _handoff.kernel is kernel:
            raise
        _cleanup_unpublished(runtime, module, primary)
        raise


def _cleanup_unpublished(
    runtime: _RuntimeModuleApi,
    module: ctypes.c_void_p,
    primary: BaseException,
) -> None:
    try:
        status = int(runtime.unload(module))
    except BaseException as cleanup:
        if not isinstance(cleanup, Exception):
            raise
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_compile_cleanup_uncertain",
            f"Unpublished guard cleanup raised {type(cleanup).__name__}.",
        ) from primary
    if status != 0:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_compile_cleanup_failed",
            "Unpublished guard cleanup failed: " + runtime.error_string(status),
        ) from primary


def _build_identity(
    *,
    architecture: str,
    options: tuple[str, ...],
    rtc_version: tuple[int, int],
    rtc_library: HipRtcLibraryIdentity,
    runtime_library: HipRuntimeLibraryIdentity,
    code_object: bytes,
) -> HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1:
    components = hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1()
    draft = HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1(
        schema_version=(
            HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_IDENTITY_SCHEMA_VERSION_V1
        ),
        abi_version=HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_ABI_VERSION_V1,
        kernel_name=HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_KERNEL_NAME_V1,
        symbol=HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1,
        kernel_abi_hash=hip_fgmres_fixed_rank_coarse_terminal_guard_abi_hash_v1(),
        recurrence_source_sha256=components["recurrence"]["sha256"],
        guard_source_sha256=components["guard"]["sha256"],
        combined_source_sha256=components["combined"]["sha256"],
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
    return validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1(
        identity
    )


def validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1(
    identity: HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1,
) -> HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1:
    if type(identity) is not HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1:
        _identity_fail("Terminal-guard identity type is invalid.")
    components = hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1()
    if (
        identity.schema_version
        != HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_IDENTITY_SCHEMA_VERSION_V1
        or identity.abi_version
        != HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_ABI_VERSION_V1
        or identity.kernel_name
        != HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_KERNEL_NAME_V1
        or identity.symbol != HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1
        or identity.kernel_abi_hash
        != hip_fgmres_fixed_rank_coarse_terminal_guard_abi_hash_v1()
        or identity.recurrence_source_sha256 != components["recurrence"]["sha256"]
        or identity.guard_source_sha256 != components["guard"]["sha256"]
        or identity.combined_source_sha256 != components["combined"]["sha256"]
        or identity.compile_options
        != (
            f"--offload-arch={identity.architecture}",
            *HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1,
        )
        or type(identity.hiprtc_version_major) is not int
        or identity.hiprtc_version_major < 0
        or type(identity.hiprtc_version_minor) is not int
        or identity.hiprtc_version_minor < 0
        or type(identity.code_object_byte_length) is not int
        or identity.code_object_byte_length <= 0
    ):
        _identity_fail("Terminal-guard identity fields are inconsistent.")
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_identity_invalid",
            exc.message,
        ) from exc
    hashes = (
        identity.kernel_abi_hash,
        identity.recurrence_source_sha256,
        identity.guard_source_sha256,
        identity.combined_source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        _identity_fail("Terminal-guard identity hashes are invalid.")
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        _identity_fail("Terminal-guard identity hash is inconsistent.")
    return identity


def _identity_payload(
    identity: HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "kernel_name": identity.kernel_name,
        "symbol": identity.symbol,
        "kernel_abi_hash": identity.kernel_abi_hash,
        "recurrence_source_sha256": identity.recurrence_source_sha256,
        "guard_source_sha256": identity.guard_source_sha256,
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


def _bounded_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_contract_invalid",
            f"{label} must be an exact int in [{minimum}, {maximum}].",
            launch_disposition="not_attempted",
        )
    return value


def _guard_runtime_pointer(value: Any, label: str) -> int:
    try:
        return _runtime_pointer(value, label)
    except HipRtcFgmresFixedRankCoarseV1Error as exc:
        raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
            "hip_rtc_fgmres_coarse_terminal_guard_pointer_invalid",
            exc.message,
            launch_disposition="not_attempted",
        ) from exc


def _identity_fail(message: str) -> None:
    raise HipRtcFgmresFixedRankCoarseTerminalGuardV1Error(
        "hip_rtc_fgmres_coarse_terminal_guard_identity_invalid",
        message,
    )


__all__ = [
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_IDENTITY_SCHEMA_VERSION_V1",
    "HIP_RTC_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_KERNEL_NAME_V1",
    "HipRtcFgmresFixedRankCoarseTerminalGuardIdentityV1",
    "HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1",
    "HipRtcFgmresFixedRankCoarseTerminalGuardV1Error",
    "compile_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_v1",
    "validate_hip_rtc_fgmres_fixed_rank_coarse_terminal_guard_identity_v1",
]
