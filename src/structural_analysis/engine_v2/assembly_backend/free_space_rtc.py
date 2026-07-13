"""Fixed-source HIPRTC owner for the device-resident free-space operator.

The three package-owned kernels materialize the reduced numeric view from
assembly-owned full buffers, form ``r = F - Kx`` and an initial direction,
and gather a full-space JVP back into free-DOF order.  Source, symbols,
compiler options, launch geometry, and native module lifetime are not caller
configurable.
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
    _pointer_integer,
    _runtime_error_string,
    _runtime_library_identity,
    _sha256_bytes,
    _validate_architecture,
    _validate_rtc_library_identity,
    _validate_runtime_identity,
    _valid_sha256,
)

HIP_RTC_FREE_SPACE_IDENTITY_SCHEMA_VERSION = (
    "structural-analysis-hip-rtc-free-space-operator-identity.v1"
)
HIP_RTC_FREE_SPACE_ABI_VERSION = 1
HIP_RTC_FREE_SPACE_KERNEL_NAME = "engine_v2_free_space_operator_v1"
HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL = "engine_v2_free_space_materialize_v1"
HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL = (
    "engine_v2_free_space_residual_direction_v1"
)
HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL = "engine_v2_free_space_gather_jvp_v1"
HIP_RTC_FREE_SPACE_BLOCK_SIZE = 256

FREE_SPACE_DEVICE_ERROR_NONE = 0
FREE_SPACE_DEVICE_ERROR_INVALID_COUNT_OR_GEOMETRY = 1
FREE_SPACE_DEVICE_ERROR_FREE_DOF_BOUNDS = 2
FREE_SPACE_DEVICE_ERROR_REDUCED_VALUE_INDEX_BOUNDS = 3
FREE_SPACE_DEVICE_ERROR_REDUCED_CSR_SEGMENT = 4
FREE_SPACE_DEVICE_ERROR_REDUCED_COLUMN_BOUNDS = 5
FREE_SPACE_DEVICE_ERROR_GLOBAL_TO_FREE_BOUNDS = 6
FREE_SPACE_DEVICE_ERROR_NONFINITE = 7

_SOURCE_RESOURCE = "kernels/engine_v2_free_space_operator_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17")
_INT32_MAX = (1 << 31) - 1
_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1


class _HipRtcFreeSpaceModuleOwnershipCell:
    """Single mutable authority cell for one native module handle."""

    __slots__ = ("module", "owner", "preowner", "lock", "unload_disposition")

    def __init__(self, module: ctypes.c_void_p) -> None:
        if type(module) is not ctypes.c_void_p or module.value:
            raise ValueError("module ownership cell requires an empty module box")
        self.module = module
        self.owner: (
            _HipRtcFreeSpaceModuleCleanupOwner | HipRtcFreeSpaceOperatorKernel | None
        ) = None
        self.preowner: _HipRtcFreeSpaceModuleCleanupOwner | None = None
        self.lock = threading.RLock()
        self.unload_disposition = "live"


class _HipRtcFreeSpaceKernelHandoff:
    """Strong evolving module/kernel owner referenced weakly by its route."""

    __slots__ = ("_cell", "_lock", "_publication_state", "__weakref__")

    def __init__(self) -> None:
        self._cell: _HipRtcFreeSpaceModuleOwnershipCell | None = None
        self._lock = threading.RLock()
        self._publication_state = "empty"

    @property
    def kernel(
        self,
    ) -> _HipRtcFreeSpaceModuleCleanupOwner | HipRtcFreeSpaceOperatorKernel | None:
        with self._lock:
            cell = self._cell
            if self._publication_state != "published" or cell is None:
                return None
            with cell.lock:
                owner = cell.owner
                if type(owner) is _HipRtcFreeSpaceModuleCleanupOwner:
                    return owner if owner.owns_module else None
                return owner if type(owner) is HipRtcFreeSpaceOperatorKernel else None

    @property
    def occupied(self) -> bool:
        with self._lock:
            return self._publication_state != "empty"

    def publish_module_owner(
        self,
        owner: _HipRtcFreeSpaceModuleCleanupOwner,
    ) -> None:
        cell = getattr(owner, "_ownership_cell", None)
        with self._lock:
            if self._publication_state != "empty" or self._cell is not None:
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_kernel_handoff_invalid",
                    "The handoff accepts one exact module owner before native load.",
                )
            self._publication_state = "reserved"
            try:
                if type(cell) is not _HipRtcFreeSpaceModuleOwnershipCell:
                    raise HipRtcFreeSpaceError(
                        "hip_rtc_free_space_kernel_handoff_invalid",
                        "The handoff accepts one exact module owner before native load.",
                    )
                with cell.lock:
                    if (
                        type(owner) is not _HipRtcFreeSpaceModuleCleanupOwner
                        or cell.owner is not owner
                        or cell.preowner is not owner
                    ):
                        raise HipRtcFreeSpaceError(
                            "hip_rtc_free_space_kernel_handoff_invalid",
                            "The handoff accepts one exact module owner before native load.",
                        )
                    self._cell = cell
                    self._publication_state = "published"
            except BaseException:
                if self._publication_state == "reserved":
                    self._publication_state = "spent"
                raise

    def promote(
        self,
        module_owner: _HipRtcFreeSpaceModuleCleanupOwner,
        kernel: HipRtcFreeSpaceOperatorKernel,
    ) -> None:
        with self._lock:
            cell = self._cell
            if (
                self._publication_state != "published"
                or type(module_owner) is not _HipRtcFreeSpaceModuleCleanupOwner
                or type(kernel) is not HipRtcFreeSpaceOperatorKernel
                or type(cell) is not _HipRtcFreeSpaceModuleOwnershipCell
                or module_owner._ownership_cell is not cell
                or kernel._ownership_cell is not cell
            ):
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_kernel_handoff_invalid",
                    "Only the published module owner can promote its exact kernel.",
                )
            _transfer_free_space_module_ownership(module_owner, kernel)


def _transfer_free_space_module_ownership(
    module_owner: _HipRtcFreeSpaceModuleCleanupOwner,
    kernel: HipRtcFreeSpaceOperatorKernel,
) -> None:
    """Atomically replace the preallocated owner with its bound kernel."""

    cell = module_owner._ownership_cell
    if type(cell) is not _HipRtcFreeSpaceModuleOwnershipCell:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_module_ownership_invalid",
            "Only the exact preallocated module owner can transfer authority.",
        )
    with cell.lock:
        if (
            kernel._ownership_cell is not cell
            or cell.owner is not module_owner
            or cell.preowner is not module_owner
            or cell.unload_disposition != "live"
            or cell.module is not module_owner._module
            or not cell.module.value
        ):
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_ownership_invalid",
                "Only a live exact preallocated owner can transfer authority.",
            )
        cell.owner = kernel


def _reclaim_free_space_module_ownership(
    module_owner: _HipRtcFreeSpaceModuleCleanupOwner,
    kernel: HipRtcFreeSpaceOperatorKernel,
) -> None:
    """Return an unpublished direct compiler kernel to its preowner."""

    cell = kernel._ownership_cell
    if type(cell) is not _HipRtcFreeSpaceModuleOwnershipCell:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_module_ownership_invalid",
            "Only the exact unpublished kernel can return module authority.",
        )
    with cell.lock:
        if (
            type(module_owner) is not _HipRtcFreeSpaceModuleCleanupOwner
            or module_owner._ownership_cell is not cell
            or cell.preowner is not module_owner
            or cell.owner is not kernel
            or cell.unload_disposition != "live"
            or not cell.module.value
        ):
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_ownership_invalid",
                "Only the exact live unpublished kernel can return authority.",
            )
        cell.owner = module_owner


class _HipRtcFreeSpaceKernelHandoffFrame:
    """One-shot weak task-local route; a stale frame owns no native resource."""

    __slots__ = ("_target_refs",)

    def __init__(self, target: _HipRtcFreeSpaceKernelHandoff) -> None:
        self._target_refs = [weakref.ref(target)]

    def claim(self) -> _HipRtcFreeSpaceKernelHandoff | None:
        try:
            target_ref = self._target_refs.pop()
        except IndexError:
            return None
        return target_ref()

    def disarm(self) -> None:
        self._target_refs.clear()


_KERNEL_HANDOFF: ContextVar[_HipRtcFreeSpaceKernelHandoffFrame | None] = ContextVar(
    "engine_v2_free_space_kernel_handoff", default=None
)


class _HipRtcFreeSpaceModuleCleanupOwner:
    """Persistent owner for a loaded module whose eager cleanup failed."""

    __slots__ = (
        "_runtime",
        "_module",
        "_ownership_cell",
        "_closed",
    )

    def __init__(
        self,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
    ) -> None:
        if not module.value:
            raise ValueError("cleanup owner requires a loaded module")
        empty_box = ctypes.c_void_p()
        cell = _HipRtcFreeSpaceModuleOwnershipCell(empty_box)
        cell.module = module
        self._runtime = runtime
        self._module = module
        self._ownership_cell = cell
        self._closed = False
        self._unload_disposition = "live"
        cell.preowner = self
        cell.owner = self

    @classmethod
    def _preallocated(
        cls,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
    ) -> _HipRtcFreeSpaceModuleCleanupOwner:
        if type(module) is not ctypes.c_void_p or module.value:
            raise ValueError("preallocated cleanup owner requires an empty module box")
        cell = _HipRtcFreeSpaceModuleOwnershipCell(module)
        owner = object.__new__(cls)
        owner._runtime = runtime
        owner._module = module
        owner._ownership_cell = cell
        owner._closed = False
        owner._unload_disposition = "live"
        cell.preowner = owner
        cell.owner = owner
        return owner

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def _unload_disposition(self) -> str:
        with self._ownership_cell.lock:
            return self._ownership_cell.unload_disposition

    @_unload_disposition.setter
    def _unload_disposition(self, value: str) -> None:
        with self._ownership_cell.lock:
            self._ownership_cell.unload_disposition = value

    @property
    def owns_module(self) -> bool:
        with self._ownership_cell.lock:
            return (
                not self._closed
                and self._ownership_cell.owner is self
                and bool(self._module.value)
            )

    def close(self) -> None:
        with self._ownership_cell.lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._closed:
            if self._ownership_cell.owner is self:
                self._finish_unload_success()
            return
        if self._ownership_cell.owner is not self:
            return
        if not self._module.value:
            self._finish_unload_success()
            return
        if self._unload_disposition == "external_unload_succeeded":
            self._finish_unload_success()
            return
        if self._unload_disposition in {
            "unload_call_inflight",
            "unload_outcome_uncertain",
        }:
            self._unload_disposition = "unload_outcome_uncertain"
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_cleanup_outcome_uncertain",
                "A prior hipModuleUnload cleanup outcome is uncertain; the module handle will not be retried.",
                cleanup_owner=self,
            )
        status: int | None = None
        self._unload_disposition = "unload_call_inflight"
        try:
            status = int(self._runtime.unload(self._module))
            if status != 0:
                self._unload_disposition = "live"
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_module_cleanup_failed",
                    "hipModuleUnload cleanup retry failed: "
                    f"{self._runtime.error_string(status)}.",
                    cleanup_owner=self,
                )
            self._unload_disposition = "external_unload_succeeded"
        except HipRtcFreeSpaceError:
            raise
        except Exception as exc:
            self._unload_disposition = (
                "external_unload_succeeded"
                if status == 0
                else ("live" if status is not None else "unload_outcome_uncertain")
            )
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_cleanup_failed",
                f"hipModuleUnload cleanup retry raised {type(exc).__name__}.",
                cleanup_owner=self,
            ) from exc
        except BaseException:
            self._unload_disposition = (
                "external_unload_succeeded"
                if status == 0
                else ("live" if status is not None else "unload_outcome_uncertain")
            )
            raise
        self._finish_unload_success()

    def _finish_unload_success(self) -> None:
        cell = self._ownership_cell
        with cell.lock:
            cell_owner = cell.owner
            if cell_owner is self:
                empty_module = ctypes.c_void_p()
                self._module = empty_module
                cell.module = empty_module
                cell.preowner = None
                self._closed = True
                cell.unload_disposition = "terminal"
                cell.owner = None
                return
            elif cell_owner is not None:
                return
            if self._closed and cell.unload_disposition == "terminal":
                return


class HipRtcFreeSpaceError(HipRtcError):
    """Stable error for the fixed free-space HIPRTC lane."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        compile_log: str = "",
        cleanup_owner: _HipRtcFreeSpaceModuleCleanupOwner | None = None,
    ) -> None:
        if cleanup_owner is not None and type(cleanup_owner) is not (
            _HipRtcFreeSpaceModuleCleanupOwner
        ):
            raise TypeError("cleanup_owner has an invalid owner type")
        self.cleanup_owner = cleanup_owner
        super().__init__(code, message, compile_log=compile_log)


@dataclass(frozen=True, slots=True)
class HipRtcFreeSpaceOperatorKernelIdentity:
    """Handle-free identity for one compiled three-symbol module."""

    schema_version: str
    abi_version: int
    kernel_name: str
    materialize_symbol: str
    residual_direction_symbol: str
    gather_jvp_symbol: str
    block_size: int
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
    def kernel_symbols(self) -> tuple[str, str, str]:
        return (
            self.materialize_symbol,
            self.residual_direction_symbol,
            self.gather_jvp_symbol,
        )

    def to_dict(self) -> dict[str, Any]:
        _validate_identity(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class HipRtcFreeSpaceOperatorKernel:
    """Loaded free-space module with explicit, retryable ownership."""

    __slots__ = (
        "_runtime",
        "_module",
        "_materialize_function",
        "_residual_direction_function",
        "_gather_jvp_function",
        "_identity",
        "_ownership_cell",
        "_closed",
    )

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        materialize_function: ctypes.c_void_p,
        residual_direction_function: ctypes.c_void_p,
        gather_jvp_function: ctypes.c_void_p,
        identity: HipRtcFreeSpaceOperatorKernelIdentity,
        ownership_cell: _HipRtcFreeSpaceModuleOwnershipCell,
    ) -> None:
        if type(ownership_cell) is not _HipRtcFreeSpaceModuleOwnershipCell:
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_ownership_invalid",
                "Kernel construction requires the exact preallocated module owner.",
            )
        with ownership_cell.lock:
            if (
                ownership_cell.module is not module
                or type(ownership_cell.owner) is not _HipRtcFreeSpaceModuleCleanupOwner
                or ownership_cell.owner._ownership_cell is not ownership_cell
                or ownership_cell.unload_disposition != "live"
                or not module.value
            ):
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_module_ownership_invalid",
                    "Kernel construction requires the exact live module owner.",
                )
        self._runtime = runtime
        self._module = module
        self._materialize_function = materialize_function
        self._residual_direction_function = residual_direction_function
        self._gather_jvp_function = gather_jvp_function
        self._identity = identity
        self._ownership_cell = ownership_cell
        self._closed = False

    @property
    def identity(self) -> HipRtcFreeSpaceOperatorKernelIdentity:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def _unload_disposition(self) -> str:
        with self._ownership_cell.lock:
            return self._ownership_cell.unload_disposition

    @_unload_disposition.setter
    def _unload_disposition(self, value: str) -> None:
        with self._ownership_cell.lock:
            self._ownership_cell.unload_disposition = value

    def __enter__(self) -> HipRtcFreeSpaceOperatorKernel:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def launch_materialize(
        self,
        stream: Any,
        global_dof_count: int,
        full_nnz_count: int,
        free_dof_count: int,
        reduced_nnz_count: int,
        free_dofs: Any,
        reduced_global_value_indices: Any,
        full_csr_values: Any,
        full_state: Any,
        full_load: Any,
        reduced_csr_values: Any,
        reduced_state: Any,
        reduced_load: Any,
        error_flag: Any,
    ) -> None:
        """Materialize the reduced numeric view from full device buffers."""

        self._require_open()
        counts = _materialize_counts(
            global_dof_count,
            full_nnz_count,
            free_dof_count,
            reduced_nnz_count,
        )
        pointers = _pointer_arguments(
            (
                ("free_dofs", free_dofs),
                (
                    "reduced_global_value_indices",
                    reduced_global_value_indices,
                ),
                ("full_csr_values", full_csr_values),
                ("full_state", full_state),
                ("full_load", full_load),
                ("reduced_csr_values", reduced_csr_values),
                ("reduced_state", reduced_state),
                ("reduced_load", reduced_load),
                ("error_flag", error_flag),
            )
        )
        work_count = max(counts[2], counts[3])
        self._launch(
            self._materialize_function,
            stream=stream,
            grid_x=_block_count(work_count),
            scalar_values=counts,
            pointer_values=pointers,
            operation="free-space materialize",
        )

    def launch_residual_direction(
        self,
        stream: Any,
        global_dof_count: int,
        free_dof_count: int,
        reduced_nnz_count: int,
        global_to_free: Any,
        reduced_row_ptr: Any,
        reduced_column_indices: Any,
        reduced_csr_values: Any,
        reduced_state: Any,
        reduced_load: Any,
        reduced_direction: Any,
        reduced_residual: Any,
        full_direction: Any,
        error_flag: Any,
    ) -> None:
        """Form the reduced residual/direction and exact constrained zeros."""

        self._require_open()
        counts = _residual_counts(
            global_dof_count,
            free_dof_count,
            reduced_nnz_count,
        )
        pointers = _pointer_arguments(
            (
                ("global_to_free", global_to_free),
                ("reduced_row_ptr", reduced_row_ptr),
                ("reduced_column_indices", reduced_column_indices),
                ("reduced_csr_values", reduced_csr_values),
                ("reduced_state", reduced_state),
                ("reduced_load", reduced_load),
                ("reduced_direction", reduced_direction),
                ("reduced_residual", reduced_residual),
                ("full_direction", full_direction),
                ("error_flag", error_flag),
            )
        )
        self._launch(
            self._residual_direction_function,
            stream=stream,
            grid_x=_block_count(counts[0]),
            scalar_values=counts,
            pointer_values=pointers,
            operation="free-space residual direction",
        )

    def launch_gather_jvp(
        self,
        stream: Any,
        global_dof_count: int,
        free_dof_count: int,
        free_dofs: Any,
        full_jvp: Any,
        reduced_jvp: Any,
        error_flag: Any,
    ) -> None:
        """Gather a full-space JVP into canonical free-DOF order."""

        self._require_open()
        counts = _free_counts(global_dof_count, free_dof_count)
        pointers = _pointer_arguments(
            (
                ("free_dofs", free_dofs),
                ("full_jvp", full_jvp),
                ("reduced_jvp", reduced_jvp),
                ("error_flag", error_flag),
            )
        )
        self._launch(
            self._gather_jvp_function,
            stream=stream,
            grid_x=_block_count(counts[1]),
            scalar_values=counts,
            pointer_values=pointers,
            operation="free-space JVP gather",
        )

    def close(self) -> None:
        """Unload once; failed unload preserves ownership for retry."""

        with self._ownership_cell.lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._closed:
            if self._ownership_cell.owner is self:
                self._finish_unload_success()
            return
        if self._ownership_cell.owner is not self:
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_ownership_changed",
                "The kernel no longer owns its native module authority.",
            )
        if self._unload_disposition == "external_unload_succeeded":
            self._finish_unload_success()
            return
        if self._unload_disposition in {
            "unload_call_inflight",
            "unload_outcome_uncertain",
        }:
            self._unload_disposition = "unload_outcome_uncertain"
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_unload_outcome_uncertain",
                "A prior hipModuleUnload outcome is uncertain; the module handle will not be retried.",
            )
        status: int | None = None
        self._unload_disposition = "unload_call_inflight"
        try:
            status = int(self._runtime.unload(self._module))
            if status != 0:
                self._unload_disposition = "live"
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_module_unload_failed",
                    f"hipModuleUnload failed: {self._runtime.error_string(status)}.",
                )
            self._unload_disposition = "external_unload_succeeded"
        except HipRtcFreeSpaceError:
            raise
        except Exception as exc:
            self._unload_disposition = (
                "external_unload_succeeded"
                if status == 0
                else ("live" if status is not None else "unload_outcome_uncertain")
            )
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_unload_failed",
                f"hipModuleUnload raised {type(exc).__name__}.",
            ) from exc
        except BaseException:
            self._unload_disposition = (
                "external_unload_succeeded"
                if status == 0
                else ("live" if status is not None else "unload_outcome_uncertain")
            )
            raise
        self._finish_unload_success()

    def _finish_unload_success(self) -> None:
        """Idempotently clear handles after one known-successful unload."""

        cell = self._ownership_cell
        with cell.lock:
            cell_owner = cell.owner
            if cell_owner is self:
                empty_module = ctypes.c_void_p()
                self._module = empty_module
                self._materialize_function = ctypes.c_void_p()
                self._residual_direction_function = ctypes.c_void_p()
                self._gather_jvp_function = ctypes.c_void_p()
                cell.module = empty_module
                preowner = cell.preowner
                if (
                    type(preowner) is _HipRtcFreeSpaceModuleCleanupOwner
                    and preowner._ownership_cell is cell
                ):
                    preowner._module = empty_module
                    preowner._closed = True
                cell.preowner = None
                self._closed = True
                cell.unload_disposition = "terminal"
                cell.owner = None
                return
            elif cell_owner is not None:
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_module_ownership_changed",
                    "The kernel ownership changed during module unload.",
                )
            if self._closed and cell.unload_disposition == "terminal":
                return
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_ownership_changed",
                "The kernel lost ownership before terminal finalization.",
            )

    def _require_open(self) -> None:
        with self._ownership_cell.lock:
            if (
                self._closed
                or self._unload_disposition != "live"
                or self._ownership_cell.owner is not self
            ):
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_kernel_closed",
                    "HIPRTC free-space operator kernel is closed or retiring.",
                )

    def _launch(
        self,
        function: ctypes.c_void_p,
        *,
        stream: Any,
        grid_x: int,
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
                    block_x=HIP_RTC_FREE_SPACE_BLOCK_SIZE,
                    stream=stream_storage,
                    parameters=parameters,
                )
            )
        except HipRtcFreeSpaceError:
            raise
        except Exception as exc:
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel failed: "
                f"{self._runtime.error_string(status)}.",
            )


def compile_hip_rtc_free_space_operator_kernel(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcFreeSpaceOperatorKernel:
    """Compile and load the package-owned three-symbol free-space module."""

    try:
        frame = _KERNEL_HANDOFF.get()
        handoff = None if frame is None else frame.claim()
        direct_handoff = handoff is None
        if handoff is None:
            handoff = _HipRtcFreeSpaceKernelHandoff()
        try:
            return _compile_free_space_operator_impl(
                loaded_runtime,
                architecture,
                hiprtc_library,
                _handoff=handoff,
            )
        except BaseException as primary:
            if direct_handoff:
                _recover_direct_free_space_compile_handoff(handoff, primary)
            raise
    except HipRtcFreeSpaceError:
        raise
    except HipRtcError as exc:
        raise HipRtcFreeSpaceError(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_unexpected_failure",
            "Unexpected HIPRTC free-space operator pipeline failure: "
            f"{type(exc).__name__}.",
        ) from exc


def _recover_direct_free_space_compile_handoff(
    handoff: _HipRtcFreeSpaceKernelHandoff,
    primary: BaseException,
) -> None:
    """Recover a direct compiler owner across its public return boundary."""

    owner = handoff.kernel
    if owner is None:
        return
    if (
        type(owner) is _HipRtcFreeSpaceModuleCleanupOwner
        and isinstance(primary, HipRtcFreeSpaceError)
        and primary.cleanup_owner is owner
    ):
        return
    if type(owner) is HipRtcFreeSpaceOperatorKernel:
        module_owner = owner._ownership_cell.preowner
        if type(module_owner) is not _HipRtcFreeSpaceModuleCleanupOwner:
            raise HipRtcFreeSpaceError(
                "hip_rtc_free_space_module_ownership_invalid",
                "The direct compiler lost its exact preallocated module owner.",
            ) from primary
        _reclaim_free_space_module_ownership(module_owner, owner)
        owner = module_owner
    if type(owner) is _HipRtcFreeSpaceModuleCleanupOwner:
        _cleanup_loaded_module(
            owner,
            primary,
            compile_log=(
                primary.compile_log if isinstance(primary, HipRtcError) else ""
            ),
        )


def _compile_free_space_operator_with_handoff(
    compiler: Any,
    handoff: _HipRtcFreeSpaceKernelHandoff,
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcFreeSpaceOperatorKernel:
    """Call the public compiler under a task-local cleanup handoff."""

    if type(handoff) is not _HipRtcFreeSpaceKernelHandoff or handoff.occupied:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_kernel_handoff_invalid",
            "An exact empty kernel handoff is required.",
        )
    frame = _HipRtcFreeSpaceKernelHandoffFrame(handoff)
    isolated_context = copy_context()

    def invoke() -> HipRtcFreeSpaceOperatorKernel:
        _KERNEL_HANDOFF.set(frame)
        return compiler(loaded_runtime, architecture, hiprtc_library)

    try:
        return isolated_context.run(invoke)
    finally:
        # The caller's Context is never mutated.  Any interruption in set(),
        # compiler return, or this local cleanup can retain at most an
        # isolated one-shot weak frame, never a kernel or caller handoff.
        frame.disarm()


def _compile_free_space_operator_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
    *,
    _handoff: _HipRtcFreeSpaceKernelHandoff | None = None,
) -> HipRtcFreeSpaceOperatorKernel:
    if _handoff is not None and (
        type(_handoff) is not _HipRtcFreeSpaceKernelHandoff or _handoff.occupied
    ):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_kernel_handoff_invalid",
            "An exact empty kernel handoff is required.",
        )
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
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_runtime_init_failed",
            f"hipInit failed: {_runtime_error_string(loaded_runtime, init_status)}.",
        )

    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(rtc, source, options)
    module = ctypes.c_void_p()
    cleanup_owner = _HipRtcFreeSpaceModuleCleanupOwner._preallocated(runtime, module)
    if _handoff is not None:
        _handoff.publish_module_owner(cleanup_owner)
    try:
        with cleanup_owner._ownership_cell.lock:
            if (
                cleanup_owner._ownership_cell.owner is not cleanup_owner
                or cleanup_owner._ownership_cell.preowner is not cleanup_owner
                or cleanup_owner._ownership_cell.module is not module
                or cleanup_owner._module is not module
                or cleanup_owner._closed
                or cleanup_owner._ownership_cell.unload_disposition != "live"
                or module.value
            ):
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_module_ownership_invalid",
                    "Native load requires the exact live preallocated module owner.",
                    compile_log=compile_log,
                )
            status = runtime.load_module_into(code_object, module)
            if status != 0 or not module.value:
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_module_load_failed",
                    f"hipModuleLoadData failed: {runtime.error_string(status)}.",
                    compile_log=compile_log,
                )
        with cleanup_owner._ownership_cell.lock:
            if (
                cleanup_owner._ownership_cell.owner is not cleanup_owner
                or cleanup_owner._ownership_cell.unload_disposition != "live"
                or not module.value
            ):
                raise HipRtcFreeSpaceError(
                    "hip_rtc_free_space_module_ownership_invalid",
                    "The compiler lost its live preallocated module owner.",
                    compile_log=compile_log,
                )
            materialize_function = _required_function(
                runtime,
                module,
                HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
                "materialize",
                compile_log,
            )
            residual_direction_function = _required_function(
                runtime,
                module,
                HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
                "residual direction",
                compile_log,
            )
            gather_jvp_function = _required_function(
                runtime,
                module,
                HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
                "JVP gather",
                compile_log,
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
        kernel = HipRtcFreeSpaceOperatorKernel(
            runtime=runtime,
            module=module,
            materialize_function=materialize_function,
            residual_direction_function=residual_direction_function,
            gather_jvp_function=gather_jvp_function,
            identity=identity,
            ownership_cell=cleanup_owner._ownership_cell,
        )
        if _handoff is not None:
            _handoff.promote(cleanup_owner, kernel)
        else:
            _transfer_free_space_module_ownership(cleanup_owner, kernel)
        return kernel
    except BaseException as primary:
        if "kernel" in locals() and _handoff is not None and _handoff.kernel is kernel:
            raise
        with cleanup_owner._ownership_cell.lock:
            if "kernel" in locals() and cleanup_owner._ownership_cell.owner is kernel:
                _reclaim_free_space_module_ownership(cleanup_owner, kernel)
        if module.value:
            _cleanup_loaded_module(
                cleanup_owner,
                primary,
                compile_log=compile_log,
            )
            raise AssertionError("unreachable")
        raise


def _required_function(
    runtime: _RuntimeModuleApi,
    module: ctypes.c_void_p,
    symbol: str,
    label: str,
    compile_log: str,
) -> ctypes.c_void_p:
    status, function = runtime.get_function(module, symbol)
    if status != 0 or not function.value:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_symbol_missing",
            f"hipModuleGetFunction failed for fixed {label} symbol "
            f"{symbol}: {runtime.error_string(status)}.",
            compile_log=compile_log,
        )
    return function


def _cleanup_loaded_module(
    cleanup_owner: _HipRtcFreeSpaceModuleCleanupOwner,
    primary: BaseException,
    *,
    compile_log: str,
) -> None:
    primary_log = (
        primary.compile_log if isinstance(primary, HipRtcError) else compile_log
    )
    try:
        cleanup_owner.close()
    except BaseException as cleanup_exc:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_module_cleanup_failed",
            f"{primary}; module cleanup raised {type(cleanup_exc).__name__}.",
            compile_log=primary_log,
            cleanup_owner=cleanup_owner,
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
) -> HipRtcFreeSpaceOperatorKernelIdentity:
    initial = HipRtcFreeSpaceOperatorKernelIdentity(
        schema_version=HIP_RTC_FREE_SPACE_IDENTITY_SCHEMA_VERSION,
        abi_version=HIP_RTC_FREE_SPACE_ABI_VERSION,
        kernel_name=HIP_RTC_FREE_SPACE_KERNEL_NAME,
        materialize_symbol=HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
        residual_direction_symbol=HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
        gather_jvp_symbol=HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
        block_size=HIP_RTC_FREE_SPACE_BLOCK_SIZE,
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
    identity: HipRtcFreeSpaceOperatorKernelIdentity,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": {
            "materialize": identity.materialize_symbol,
            "residual_direction": identity.residual_direction_symbol,
            "gather_jvp": identity.gather_jvp_symbol,
        },
        "launch_geometry": {"block_size": identity.block_size},
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
    if type(identity) is not HipRtcFreeSpaceOperatorKernelIdentity:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            "Free-space operator identity type is invalid.",
        )
    integer_fields = (
        identity.abi_version,
        identity.block_size,
        identity.hiprtc_version_major,
        identity.hiprtc_version_minor,
        identity.code_object_byte_length,
    )
    string_fields = (
        identity.schema_version,
        identity.kernel_name,
        identity.materialize_symbol,
        identity.residual_direction_symbol,
        identity.gather_jvp_symbol,
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
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            "Free-space identity fields require exact scalar and tuple types.",
        )
    if (
        identity.schema_version != HIP_RTC_FREE_SPACE_IDENTITY_SCHEMA_VERSION
        or identity.abi_version != HIP_RTC_FREE_SPACE_ABI_VERSION
        or identity.kernel_name != HIP_RTC_FREE_SPACE_KERNEL_NAME
        or identity.materialize_symbol != HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL
        or identity.residual_direction_symbol
        != HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL
        or identity.gather_jvp_symbol != HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL
        or identity.block_size != HIP_RTC_FREE_SPACE_BLOCK_SIZE
        or identity.source_resource != _SOURCE_RESOURCE
    ):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            "Fixed free-space operator ABI identity is invalid.",
        )
    if identity.source_sha256 != _sha256_bytes(_fixed_source()):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            "Free-space source hash does not match package-owned source.",
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            exc.message,
        ) from exc
    expected_options = (
        f"--offload-arch={identity.architecture}",
        *_FIXED_OPTION_SUFFIX,
    )
    if identity.compile_options != expected_options:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            "Free-space operator compile options are not fixed.",
        )
    hashes = (
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            "Free-space operator identity has an invalid SHA-256.",
        )
    if (
        identity.hiprtc_version_major < 0
        or identity.hiprtc_version_minor < 0
        or identity.code_object_byte_length <= 0
    ):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_invalid",
            "Free-space version or code-object length is invalid.",
        )
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_identity_hash_mismatch",
            "Free-space operator identity hash is invalid.",
        )


def _fixed_source() -> bytes:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_source_missing",
            "The package-owned free-space source is unavailable: "
            f"{type(exc).__name__}.",
        ) from exc
    symbols = (
        HIP_RTC_FREE_SPACE_MATERIALIZE_SYMBOL,
        HIP_RTC_FREE_SPACE_RESIDUAL_DIRECTION_SYMBOL,
        HIP_RTC_FREE_SPACE_GATHER_JVP_SYMBOL,
    )
    if not source or any(
        source.count(symbol.encode("ascii")) != 1 for symbol in symbols
    ):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_source_invalid",
            "The package-owned free-space source must contain all fixed "
            "symbols exactly once.",
        )
    return source


def _materialize_counts(
    global_dof_count: Any,
    full_nnz_count: Any,
    free_dof_count: Any,
    reduced_nnz_count: Any,
) -> tuple[int, int, int, int]:
    counts = (
        _positive_int32(global_dof_count, "global_dof_count"),
        _positive_int32(full_nnz_count, "full_nnz_count"),
        _positive_int32(free_dof_count, "free_dof_count"),
        _positive_int32(reduced_nnz_count, "reduced_nnz_count"),
    )
    if counts[2] > counts[0] or counts[3] > counts[1]:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_launch_contract_invalid",
            "Reduced counts must not exceed their full-space counts.",
        )
    return counts


def _residual_counts(
    global_dof_count: Any,
    free_dof_count: Any,
    reduced_nnz_count: Any,
) -> tuple[int, int, int]:
    free_counts = _free_counts(global_dof_count, free_dof_count)
    return (
        *free_counts,
        _positive_int32(reduced_nnz_count, "reduced_nnz_count"),
    )


def _free_counts(
    global_dof_count: Any,
    free_dof_count: Any,
) -> tuple[int, int]:
    counts = (
        _positive_int32(global_dof_count, "global_dof_count"),
        _positive_int32(free_dof_count, "free_dof_count"),
    )
    if counts[1] > counts[0]:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_launch_contract_invalid",
            "free_dof_count must not exceed global_dof_count.",
        )
    return counts


def _positive_int32(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= _INT32_MAX
    ):
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_launch_contract_invalid",
            f"{label} must be a positive signed int32 value.",
        )
    return value


def _block_count(work_count: int) -> int:
    return (
        work_count + HIP_RTC_FREE_SPACE_BLOCK_SIZE - 1
    ) // HIP_RTC_FREE_SPACE_BLOCK_SIZE


def _pointer_arguments(
    values: tuple[tuple[str, Any], ...],
) -> tuple[int, ...]:
    return tuple(_runtime_pointer(value, label) for label, value in values)


def _runtime_pointer(value: Any, label: str) -> int:
    try:
        pointer = _pointer_integer(value, label)
    except HipRtcError as exc:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_launch_contract_invalid",
            exc.message,
        ) from exc
    if pointer > _UINTPTR_MAX:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_launch_contract_invalid",
            f"{label} exceeds the native uintptr capacity.",
        )
    packed = ctypes.c_void_p(pointer)
    if packed.value != pointer:
        raise HipRtcFreeSpaceError(
            "hip_rtc_free_space_launch_contract_invalid",
            f"{label} does not round-trip through ctypes.c_void_p.",
        )
    return pointer
