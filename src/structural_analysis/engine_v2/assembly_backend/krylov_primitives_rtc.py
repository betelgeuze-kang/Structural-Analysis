"""Fixed-source HIPRTC owner for deterministic Krylov primitives.

The package owns all nine symbols, source bytes, compiler options, launch
geometry, and native module lifetime.  Reductions consume contiguous
512-value segments using a fixed 256-thread shared-memory tree.  No caller
source, launch geometry, or numerical reduction policy is configurable.
"""

from __future__ import annotations

import ctypes
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field, replace
import math
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

HIP_RTC_KRYLOV_PRIMITIVES_IDENTITY_SCHEMA_VERSION = (
    "structural-analysis-hip-rtc-krylov-primitives-identity.v1"
)
HIP_RTC_KRYLOV_PRIMITIVES_ABI_VERSION = 1
HIP_RTC_KRYLOV_PRIMITIVES_KERNEL_NAME = "engine_v2_krylov_primitives_v1"
HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL = "prepare_positive_jacobi"
HIP_RTC_KRYLOV_FILL_SYMBOL = "fill"
HIP_RTC_KRYLOV_AFFINE_SYMBOL = "affine"
HIP_RTC_KRYLOV_APPLY_JACOBI_SYMBOL = "apply_jacobi"
HIP_RTC_KRYLOV_DOT_STAGE_SYMBOL = "dot_stage"
HIP_RTC_KRYLOV_SUM_STAGE_SYMBOL = "sum_stage"
HIP_RTC_KRYLOV_LASSQ_STAGE_SYMBOL = "lassq_stage"
HIP_RTC_KRYLOV_LASSQ_COMBINE_STAGE_SYMBOL = "lassq_combine_stage"
HIP_RTC_KRYLOV_LASSQ_FINALIZE_SYMBOL = "lassq_finalize"
HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE = 256
HIP_RTC_KRYLOV_REDUCTION_VALUES_PER_BLOCK = 512

KRYLOV_DEVICE_ERROR_NONE = 0
KRYLOV_DEVICE_ERROR_INVALID_COUNT_OR_GEOMETRY = 1 << 0
KRYLOV_DEVICE_ERROR_CSR_STRUCTURE = 1 << 1
KRYLOV_DEVICE_ERROR_JACOBI_DIAGONAL = 1 << 2
KRYLOV_DEVICE_ERROR_NONFINITE_INPUT = 1 << 3
KRYLOV_DEVICE_ERROR_ARITHMETIC_OVERFLOW = 1 << 4
KRYLOV_DEVICE_ERROR_INVALID_LASSQ_PAIR = 1 << 5

_SOURCE_RESOURCE = "kernels/engine_v2_krylov_primitives_v1.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17", "-ffp-contract=off")
_INT32_MAX = (1 << 31) - 1
_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1


class _HipRtcKrylovPrimitivesModuleOwnershipCell:
    """Single mutable authority cell for one native module handle."""

    __slots__ = ("module", "owner", "preowner", "lock", "unload_disposition")

    def __init__(self, module: ctypes.c_void_p) -> None:
        if type(module) is not ctypes.c_void_p or module.value:
            raise ValueError("module ownership cell requires an empty module box")
        self.module = module
        self.owner: (
            _HipRtcKrylovPrimitivesModuleCleanupOwner
            | HipRtcKrylovPrimitivesKernel
            | None
        ) = None
        self.preowner: _HipRtcKrylovPrimitivesModuleCleanupOwner | None = None
        self.lock = threading.RLock()
        self.unload_disposition = "live"


class _HipRtcKrylovPrimitivesKernelHandoff:
    """Strong evolving module/kernel owner referenced weakly by its route."""

    __slots__ = ("_cell", "_lock", "_publication_state", "__weakref__")

    def __init__(self) -> None:
        self._cell: _HipRtcKrylovPrimitivesModuleOwnershipCell | None = None
        self._lock = threading.RLock()
        self._publication_state = "empty"

    @property
    def kernel(
        self,
    ) -> (
        _HipRtcKrylovPrimitivesModuleCleanupOwner | HipRtcKrylovPrimitivesKernel | None
    ):
        with self._lock:
            cell = self._cell
            if self._publication_state != "published" or cell is None:
                return None
            with cell.lock:
                owner = cell.owner
                if type(owner) is _HipRtcKrylovPrimitivesModuleCleanupOwner:
                    return owner if owner.owns_module else None
                return owner if type(owner) is HipRtcKrylovPrimitivesKernel else None

    @property
    def occupied(self) -> bool:
        with self._lock:
            return self._publication_state != "empty"

    def publish_module_owner(
        self,
        owner: _HipRtcKrylovPrimitivesModuleCleanupOwner,
    ) -> None:
        cell = getattr(owner, "_ownership_cell", None)
        with self._lock:
            if self._publication_state != "empty" or self._cell is not None:
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_kernel_handoff_invalid",
                    "The handoff accepts one exact module owner before native load.",
                )
            self._publication_state = "reserved"
            try:
                if type(cell) is not _HipRtcKrylovPrimitivesModuleOwnershipCell:
                    raise HipRtcKrylovPrimitivesError(
                        "hip_rtc_krylov_primitives_kernel_handoff_invalid",
                        "The handoff accepts one exact module owner before native load.",
                    )
                with cell.lock:
                    if (
                        type(owner) is not _HipRtcKrylovPrimitivesModuleCleanupOwner
                        or cell.owner is not owner
                        or cell.preowner is not owner
                    ):
                        raise HipRtcKrylovPrimitivesError(
                            "hip_rtc_krylov_primitives_kernel_handoff_invalid",
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
        module_owner: _HipRtcKrylovPrimitivesModuleCleanupOwner,
        kernel: HipRtcKrylovPrimitivesKernel,
    ) -> None:
        with self._lock:
            cell = self._cell
            if (
                self._publication_state != "published"
                or type(module_owner) is not _HipRtcKrylovPrimitivesModuleCleanupOwner
                or type(kernel) is not HipRtcKrylovPrimitivesKernel
                or type(cell) is not _HipRtcKrylovPrimitivesModuleOwnershipCell
                or module_owner._ownership_cell is not cell
                or kernel._ownership_cell is not cell
            ):
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_kernel_handoff_invalid",
                    "Only the published module owner can promote its exact kernel.",
                )
            _transfer_krylov_primitives_module_ownership(module_owner, kernel)


def _transfer_krylov_primitives_module_ownership(
    module_owner: _HipRtcKrylovPrimitivesModuleCleanupOwner,
    kernel: HipRtcKrylovPrimitivesKernel,
) -> None:
    """Atomically replace the preallocated owner with its bound kernel."""

    cell = module_owner._ownership_cell
    if type(cell) is not _HipRtcKrylovPrimitivesModuleOwnershipCell:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_module_ownership_invalid",
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
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_ownership_invalid",
                "Only a live exact preallocated owner can transfer authority.",
            )
        cell.owner = kernel


def _reclaim_krylov_primitives_module_ownership(
    module_owner: _HipRtcKrylovPrimitivesModuleCleanupOwner,
    kernel: HipRtcKrylovPrimitivesKernel,
) -> None:
    """Return an unpublished direct compiler kernel to its preowner."""

    cell = kernel._ownership_cell
    if type(cell) is not _HipRtcKrylovPrimitivesModuleOwnershipCell:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_module_ownership_invalid",
            "Only the exact unpublished kernel can return module authority.",
        )
    with cell.lock:
        if (
            type(module_owner) is not _HipRtcKrylovPrimitivesModuleCleanupOwner
            or module_owner._ownership_cell is not cell
            or cell.preowner is not module_owner
            or cell.owner is not kernel
            or cell.unload_disposition != "live"
            or not cell.module.value
        ):
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_ownership_invalid",
                "Only the exact live unpublished kernel can return authority.",
            )
        cell.owner = module_owner


class _HipRtcKrylovPrimitivesKernelHandoffFrame:
    """One-shot weak task-local route; a stale frame owns no native resource."""

    __slots__ = ("_target_refs",)

    def __init__(self, target: _HipRtcKrylovPrimitivesKernelHandoff) -> None:
        self._target_refs = [weakref.ref(target)]

    def claim(self) -> _HipRtcKrylovPrimitivesKernelHandoff | None:
        try:
            target_ref = self._target_refs.pop()
        except IndexError:
            return None
        return target_ref()

    def disarm(self) -> None:
        self._target_refs.clear()


_KERNEL_HANDOFF: ContextVar[_HipRtcKrylovPrimitivesKernelHandoffFrame | None] = (
    ContextVar("engine_v2_krylov_primitives_kernel_handoff", default=None)
)

_SYMBOL_ITEMS = (
    ("prepare_positive_jacobi", HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL),
    ("fill", HIP_RTC_KRYLOV_FILL_SYMBOL),
    ("affine", HIP_RTC_KRYLOV_AFFINE_SYMBOL),
    ("apply_jacobi", HIP_RTC_KRYLOV_APPLY_JACOBI_SYMBOL),
    ("dot_stage", HIP_RTC_KRYLOV_DOT_STAGE_SYMBOL),
    ("sum_stage", HIP_RTC_KRYLOV_SUM_STAGE_SYMBOL),
    ("lassq_stage", HIP_RTC_KRYLOV_LASSQ_STAGE_SYMBOL),
    ("lassq_combine_stage", HIP_RTC_KRYLOV_LASSQ_COMBINE_STAGE_SYMBOL),
    ("lassq_finalize", HIP_RTC_KRYLOV_LASSQ_FINALIZE_SYMBOL),
)


class HipRtcKrylovPrimitivesError(HipRtcError):
    """Stable fail-closed error for the fixed Krylov primitive lane."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        compile_log: str = "",
        cleanup_owner: _HipRtcKrylovPrimitivesModuleCleanupOwner | None = None,
    ) -> None:
        if cleanup_owner is not None and type(cleanup_owner) is not (
            _HipRtcKrylovPrimitivesModuleCleanupOwner
        ):
            raise TypeError("cleanup_owner has an invalid owner type")
        self.cleanup_owner = cleanup_owner
        super().__init__(code, message, compile_log=compile_log)


class _HipRtcKrylovPrimitivesModuleCleanupOwner:
    """Retryable owner for a loaded module whose eager cleanup failed."""

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
        cell = _HipRtcKrylovPrimitivesModuleOwnershipCell(empty_box)
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
    ) -> _HipRtcKrylovPrimitivesModuleCleanupOwner:
        if type(module) is not ctypes.c_void_p or module.value:
            raise ValueError("preallocated cleanup owner requires an empty module box")
        cell = _HipRtcKrylovPrimitivesModuleOwnershipCell(module)
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
        """Retry module unload without discarding ownership on failure."""

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
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_cleanup_outcome_uncertain",
                "A prior hipModuleUnload cleanup outcome is uncertain; the module handle will not be retried.",
                cleanup_owner=self,
            )
        status: int | None = None
        self._unload_disposition = "unload_call_inflight"
        try:
            status = int(self._runtime.unload(self._module))
            if status != 0:
                self._unload_disposition = "live"
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_module_cleanup_failed",
                    "hipModuleUnload cleanup retry failed: "
                    f"{self._runtime.error_string(status)}.",
                    cleanup_owner=self,
                )
            self._unload_disposition = "external_unload_succeeded"
        except HipRtcKrylovPrimitivesError:
            raise
        except Exception as exc:
            self._unload_disposition = (
                "external_unload_succeeded"
                if status == 0
                else ("live" if status is not None else "unload_outcome_uncertain")
            )
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_cleanup_failed",
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


@dataclass(frozen=True, slots=True)
class HipRtcKrylovPrimitivesKernelIdentity:
    """Handle-free identity for one compiled nine-symbol module."""

    schema_version: str
    abi_version: int
    kernel_name: str
    prepare_positive_jacobi_symbol: str
    fill_symbol: str
    affine_symbol: str
    apply_jacobi_symbol: str
    dot_stage_symbol: str
    sum_stage_symbol: str
    lassq_stage_symbol: str
    lassq_combine_stage_symbol: str
    lassq_finalize_symbol: str
    block_size: int
    reduction_values_per_block: int
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

    @property
    def kernel_symbols(self) -> tuple[str, ...]:
        return (
            self.prepare_positive_jacobi_symbol,
            self.fill_symbol,
            self.affine_symbol,
            self.apply_jacobi_symbol,
            self.dot_stage_symbol,
            self.sum_stage_symbol,
            self.lassq_stage_symbol,
            self.lassq_combine_stage_symbol,
            self.lassq_finalize_symbol,
        )

    def to_dict(self) -> dict[str, Any]:
        _validate_identity(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


class HipRtcKrylovPrimitivesKernel:
    """Loaded deterministic primitive module with fenced ownership.

    Every successful or outcome-ambiguous launch records its stream as pending.
    The owner that observes a completion fence must acknowledge that exact stream
    before module unload.  This low-level contract prevents destruction of code
    objects while device work may still reference them.
    """

    __slots__ = (
        "_runtime",
        "_module",
        "_functions",
        "_identity",
        "_ownership_cell",
        "_closed",
        "_pending_streams",
    )

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        functions: dict[str, ctypes.c_void_p],
        identity: HipRtcKrylovPrimitivesKernelIdentity,
        ownership_cell: _HipRtcKrylovPrimitivesModuleOwnershipCell,
    ) -> None:
        if type(ownership_cell) is not _HipRtcKrylovPrimitivesModuleOwnershipCell:
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_ownership_invalid",
                "Kernel construction requires the exact preallocated module owner.",
            )
        with ownership_cell.lock:
            if (
                ownership_cell.module is not module
                or type(ownership_cell.owner)
                is not _HipRtcKrylovPrimitivesModuleCleanupOwner
                or ownership_cell.owner._ownership_cell is not ownership_cell
                or ownership_cell.unload_disposition != "live"
                or not module.value
            ):
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_module_ownership_invalid",
                    "Kernel construction requires the exact live module owner.",
                )
        self._runtime = runtime
        self._module = module
        self._functions = dict(functions)
        self._identity = identity
        self._ownership_cell = ownership_cell
        self._closed = False
        self._pending_streams: dict[int, int] = {}

    @property
    def identity(self) -> HipRtcKrylovPrimitivesKernelIdentity:
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

    @property
    def pending_stream_count(self) -> int:
        """Return the number of streams still requiring a completion fence."""

        return len(self._pending_streams)

    def __enter__(self) -> HipRtcKrylovPrimitivesKernel:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def launch_prepare_positive_jacobi(
        self,
        stream: Any,
        n: int,
        nnz: int,
        row_ptr: Any,
        column_indices: Any,
        values: Any,
        inverse_diagonal: Any,
        error_flag: Any,
    ) -> None:
        """Build an unclamped inverse for exactly-one positive diagonals."""

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
                ("inverse_diagonal", inverse_diagonal),
                ("error_flag", error_flag),
            )
        )
        self._launch(
            "prepare_positive_jacobi",
            stream=stream,
            grid_x=_vector_block_count(checked_n),
            arguments=(
                ctypes.c_int(checked_n),
                ctypes.c_int(checked_nnz),
                *tuple(ctypes.c_void_p(value) for value in pointers),
            ),
            operation="positive Jacobi preparation",
        )

    def launch_fill(
        self,
        stream: Any,
        n: int,
        value: float,
        output: Any,
        error_flag: Any,
    ) -> None:
        """Fill one device vector, canonicalizing signed zero to +0.0."""

        self._require_open()
        checked_n = _positive_int32(n, "n")
        checked_value = _finite_float64(value, "value")
        pointers = _pointer_arguments((("output", output), ("error_flag", error_flag)))
        self._launch(
            "fill",
            stream=stream,
            grid_x=_vector_block_count(checked_n),
            arguments=(
                ctypes.c_int(checked_n),
                ctypes.c_double(checked_value),
                *tuple(ctypes.c_void_p(item) for item in pointers),
            ),
            operation="vector fill",
        )

    def launch_affine(
        self,
        stream: Any,
        n: int,
        alpha: float,
        x: Any,
        beta: float,
        y: Any,
        output: Any,
        error_flag: Any,
    ) -> None:
        """Compute ``output = alpha*x + beta*y`` with x/y alias safety."""

        self._require_open()
        checked_n = _positive_int32(n, "n")
        checked_alpha = _finite_float64(alpha, "alpha")
        checked_beta = _finite_float64(beta, "beta")
        pointers = _pointer_arguments(
            (
                ("x", x),
                ("y", y),
                ("output", output),
                ("error_flag", error_flag),
            )
        )
        self._launch(
            "affine",
            stream=stream,
            grid_x=_vector_block_count(checked_n),
            arguments=(
                ctypes.c_int(checked_n),
                ctypes.c_double(checked_alpha),
                ctypes.c_void_p(pointers[0]),
                ctypes.c_double(checked_beta),
                ctypes.c_void_p(pointers[1]),
                ctypes.c_void_p(pointers[2]),
                ctypes.c_void_p(pointers[3]),
            ),
            operation="vector affine",
        )

    def launch_apply_jacobi(
        self,
        stream: Any,
        n: int,
        inverse_diagonal: Any,
        x: Any,
        output: Any,
        error_flag: Any,
    ) -> None:
        """Apply a finite positive inverse Jacobi diagonal."""

        self._require_open()
        checked_n = _positive_int32(n, "n")
        pointers = _pointer_arguments(
            (
                ("inverse_diagonal", inverse_diagonal),
                ("x", x),
                ("output", output),
                ("error_flag", error_flag),
            )
        )
        self._launch_vector_pointers(
            "apply_jacobi",
            stream,
            checked_n,
            pointers,
            "Jacobi application",
        )

    def launch_dot_stage(
        self,
        stream: Any,
        n: int,
        x: Any,
        y: Any,
        partial: Any,
        error_flag: Any,
    ) -> None:
        """Reduce dot products into deterministic scalar partials."""

        self._require_open()
        checked_n = _positive_int32(n, "n")
        pointers = _pointer_arguments(
            (
                ("x", x),
                ("y", y),
                ("partial", partial),
                ("error_flag", error_flag),
            )
        )
        self._launch_reduction_pointers(
            "dot_stage", stream, checked_n, pointers, "dot reduction stage"
        )

    def launch_sum_stage(
        self,
        stream: Any,
        n: int,
        input_values: Any,
        partial: Any,
        error_flag: Any,
    ) -> None:
        """Reduce scalar partials by the same deterministic tree."""

        self._require_open()
        checked_n = _positive_int32(n, "n")
        pointers = _pointer_arguments(
            (
                ("input_values", input_values),
                ("partial", partial),
                ("error_flag", error_flag),
            )
        )
        self._launch_reduction_pointers(
            "sum_stage", stream, checked_n, pointers, "sum reduction stage"
        )

    def launch_lassq_stage(
        self,
        stream: Any,
        n: int,
        x: Any,
        partial_pairs: Any,
        error_flag: Any,
    ) -> None:
        """Reduce vector values into stable deterministic LASSQ pairs."""

        self._require_open()
        checked_n = _positive_int32(n, "n")
        pointers = _pointer_arguments(
            (
                ("x", x),
                ("partial_pairs", partial_pairs),
                ("error_flag", error_flag),
            )
        )
        self._launch_reduction_pointers(
            "lassq_stage", stream, checked_n, pointers, "LASSQ reduction stage"
        )

    def launch_lassq_combine_stage(
        self,
        stream: Any,
        n: int,
        input_pairs: Any,
        output_pairs: Any,
        error_flag: Any,
    ) -> None:
        """Reduce LASSQ pairs into another deterministic pair level."""

        self._require_open()
        checked_n = _positive_int32(n, "n")
        pointers = _pointer_arguments(
            (
                ("input_pairs", input_pairs),
                ("output_pairs", output_pairs),
                ("error_flag", error_flag),
            )
        )
        self._launch_reduction_pointers(
            "lassq_combine_stage",
            stream,
            checked_n,
            pointers,
            "LASSQ pair combine stage",
        )

    def launch_lassq_finalize(
        self,
        stream: Any,
        pair: Any,
        norm: Any,
        error_flag: Any,
    ) -> None:
        """Finalize one LASSQ pair into a stable L2 norm."""

        self._require_open()
        pointers = _pointer_arguments(
            (("pair", pair), ("norm", norm), ("error_flag", error_flag))
        )
        self._launch(
            "lassq_finalize",
            stream=stream,
            grid_x=1,
            arguments=tuple(ctypes.c_void_p(item) for item in pointers),
            operation="LASSQ finalize",
        )

    def acknowledge_stream_completion(self, stream: Any) -> None:
        """Acknowledge that an external fence completed one exact stream.

        The caller must invoke this only after a successful synchronization or
        an equivalent completion event for ``stream``.  Unknown streams are a
        contract error so a fence for one queue cannot clear another queue.
        """

        self._require_open()
        stream_value = _runtime_pointer(stream, "stream")
        if stream_value not in self._pending_streams:
            raise _launch_contract_error(
                "stream has no pending Krylov primitive launch to acknowledge."
            )
        del self._pending_streams[stream_value]

    def close(self) -> None:
        """Unload only after every launched stream has an acknowledged fence."""

        with self._ownership_cell.lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._closed:
            if self._ownership_cell.owner is self:
                self._finish_unload_success()
            return
        if self._ownership_cell.owner is not self:
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_ownership_changed",
                "The kernel no longer owns its native module authority.",
            )
        if self._pending_streams:
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_completion_fence_required",
                "HIPRTC Krylov primitive module has pending stream work; "
                "acknowledge an observed completion fence before unload.",
            )
        if self._unload_disposition == "external_unload_succeeded":
            self._finish_unload_success()
            return
        if self._unload_disposition in {
            "unload_call_inflight",
            "unload_outcome_uncertain",
        }:
            self._unload_disposition = "unload_outcome_uncertain"
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_unload_outcome_uncertain",
                "A prior hipModuleUnload outcome is uncertain; the module handle will not be retried.",
            )
        status: int | None = None
        self._unload_disposition = "unload_call_inflight"
        try:
            status = int(self._runtime.unload(self._module))
            if status != 0:
                self._unload_disposition = "live"
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_module_unload_failed",
                    f"hipModuleUnload failed: {self._runtime.error_string(status)}.",
                )
            self._unload_disposition = "external_unload_succeeded"
        except HipRtcKrylovPrimitivesError:
            raise
        except Exception as exc:
            self._unload_disposition = (
                "external_unload_succeeded"
                if status == 0
                else ("live" if status is not None else "unload_outcome_uncertain")
            )
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_unload_failed",
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
                self._functions.clear()
                self._pending_streams.clear()
                cell.module = empty_module
                preowner = cell.preowner
                if (
                    type(preowner) is _HipRtcKrylovPrimitivesModuleCleanupOwner
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
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_module_ownership_changed",
                    "The kernel ownership changed during module unload.",
                )
            if self._closed and cell.unload_disposition == "terminal":
                return
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_ownership_changed",
                "The kernel lost ownership before terminal finalization.",
            )

    def _require_open(self) -> None:
        with self._ownership_cell.lock:
            if (
                self._closed
                or self._unload_disposition != "live"
                or self._ownership_cell.owner is not self
            ):
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_kernel_closed",
                    "HIPRTC Krylov primitive kernel is closed or retiring.",
                )

    def _launch_vector_pointers(
        self,
        function_name: str,
        stream: Any,
        n: int,
        pointers: tuple[int, ...],
        operation: str,
    ) -> None:
        self._launch(
            function_name,
            stream=stream,
            grid_x=_vector_block_count(n),
            arguments=(
                ctypes.c_int(n),
                *tuple(ctypes.c_void_p(item) for item in pointers),
            ),
            operation=operation,
        )

    def _launch_reduction_pointers(
        self,
        function_name: str,
        stream: Any,
        n: int,
        pointers: tuple[int, ...],
        operation: str,
    ) -> None:
        self._launch(
            function_name,
            stream=stream,
            grid_x=reduction_output_count(n),
            arguments=(
                ctypes.c_int(n),
                *tuple(ctypes.c_void_p(item) for item in pointers),
            ),
            operation=operation,
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
        stream_storage = ctypes.c_void_p(stream_value)
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
                    block_x=HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE,
                    stream=stream_storage,
                    parameters=parameters,
                )
            )
        except HipRtcKrylovPrimitivesError:
            raise
        except Exception as exc:
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
            ) from exc
        if status != 0:
            pending_count = self._pending_streams[stream_value] - 1
            if pending_count:
                self._pending_streams[stream_value] = pending_count
            else:
                del self._pending_streams[stream_value]
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_kernel_launch_failed",
                f"{operation} hipModuleLaunchKernel failed: "
                f"{self._runtime.error_string(status)}.",
            )


def reduction_output_count(value_count: int) -> int:
    """Return the fixed number of partials for one reduction stage."""

    checked_count = _positive_int32(value_count, "value_count")
    return (
        checked_count + HIP_RTC_KRYLOV_REDUCTION_VALUES_PER_BLOCK - 1
    ) // HIP_RTC_KRYLOV_REDUCTION_VALUES_PER_BLOCK


def compile_hip_rtc_krylov_primitives_kernel(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcKrylovPrimitivesKernel:
    """Compile and load the package-owned nine-symbol primitive module."""

    try:
        frame = _KERNEL_HANDOFF.get()
        handoff = None if frame is None else frame.claim()
        direct_handoff = handoff is None
        if handoff is None:
            handoff = _HipRtcKrylovPrimitivesKernelHandoff()
        try:
            return _compile_krylov_primitives_impl(
                loaded_runtime,
                architecture,
                hiprtc_library,
                _handoff=handoff,
            )
        except BaseException as primary:
            if direct_handoff:
                _recover_direct_krylov_primitives_compile_handoff(
                    handoff,
                    primary,
                )
            raise
    except HipRtcKrylovPrimitivesError:
        raise
    except HipRtcError as exc:
        raise HipRtcKrylovPrimitivesError(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_unexpected_failure",
            "Unexpected HIPRTC Krylov primitive pipeline failure: "
            f"{type(exc).__name__}.",
        ) from exc


def _recover_direct_krylov_primitives_compile_handoff(
    handoff: _HipRtcKrylovPrimitivesKernelHandoff,
    primary: BaseException,
) -> None:
    """Recover a direct compiler owner across its public return boundary."""

    owner = handoff.kernel
    if owner is None:
        return
    if (
        type(owner) is _HipRtcKrylovPrimitivesModuleCleanupOwner
        and isinstance(primary, HipRtcKrylovPrimitivesError)
        and primary.cleanup_owner is owner
    ):
        return
    if type(owner) is HipRtcKrylovPrimitivesKernel:
        module_owner = owner._ownership_cell.preowner
        if type(module_owner) is not _HipRtcKrylovPrimitivesModuleCleanupOwner:
            raise HipRtcKrylovPrimitivesError(
                "hip_rtc_krylov_primitives_module_ownership_invalid",
                "The direct compiler lost its exact preallocated module owner.",
            ) from primary
        _reclaim_krylov_primitives_module_ownership(module_owner, owner)
        owner = module_owner
    if type(owner) is _HipRtcKrylovPrimitivesModuleCleanupOwner:
        _cleanup_loaded_module(
            owner,
            primary,
            compile_log=(
                primary.compile_log if isinstance(primary, HipRtcError) else ""
            ),
        )


def _compile_krylov_primitives_with_handoff(
    compiler: Any,
    handoff: _HipRtcKrylovPrimitivesKernelHandoff,
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcKrylovPrimitivesKernel:
    """Call the public compiler under a task-local cleanup handoff."""

    if type(handoff) is not _HipRtcKrylovPrimitivesKernelHandoff or handoff.occupied:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_kernel_handoff_invalid",
            "An exact empty kernel handoff is required.",
        )
    frame = _HipRtcKrylovPrimitivesKernelHandoffFrame(handoff)
    isolated_context = copy_context()

    def invoke() -> HipRtcKrylovPrimitivesKernel:
        _KERNEL_HANDOFF.set(frame)
        return compiler(loaded_runtime, architecture, hiprtc_library)

    try:
        return isolated_context.run(invoke)
    finally:
        # The caller context remains untouched across every interruption
        # boundary; only a one-shot weak frame exists in the private copy.
        frame.disarm()


def _compile_krylov_primitives_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
    *,
    _handoff: _HipRtcKrylovPrimitivesKernelHandoff | None = None,
) -> HipRtcKrylovPrimitivesKernel:
    if _handoff is not None and (
        type(_handoff) is not _HipRtcKrylovPrimitivesKernelHandoff or _handoff.occupied
    ):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_kernel_handoff_invalid",
            "An exact empty kernel handoff is required.",
        )
    checked_architecture = _validate_architecture(architecture)
    runtime_identity = _runtime_library_identity(loaded_runtime)
    source = _fixed_source()
    source_hash = _sha256_bytes(source)
    options = (f"--offload-arch={checked_architecture}", *_FIXED_OPTION_SUFFIX)

    rtc = _load_hiprtc_api(hiprtc_library)
    status, rtc_major, rtc_minor = rtc.version()
    if status != 0 or rtc_major < 0 or rtc_minor < 0:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_runtime_init_failed",
            f"hipInit failed: {_runtime_error_string(loaded_runtime, init_status)}.",
        )

    runtime = _RuntimeModuleApi(loaded_runtime)
    code_object, compile_log = _compile_fixed_source(
        rtc,
        source,
        options,
        program_name=Path(_SOURCE_RESOURCE).name,
    )
    module = ctypes.c_void_p()
    cleanup_owner = _HipRtcKrylovPrimitivesModuleCleanupOwner._preallocated(
        runtime,
        module,
    )
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
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_module_ownership_invalid",
                    "Native load requires the exact live preallocated module owner.",
                    compile_log=compile_log,
                )
            status = runtime.load_module_into(code_object, module)
            if status != 0 or not module.value:
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_module_load_failed",
                    f"hipModuleLoadData failed: {runtime.error_string(status)}.",
                    compile_log=compile_log,
                )
        with cleanup_owner._ownership_cell.lock:
            if (
                cleanup_owner._ownership_cell.owner is not cleanup_owner
                or cleanup_owner._ownership_cell.unload_disposition != "live"
                or not module.value
            ):
                raise HipRtcKrylovPrimitivesError(
                    "hip_rtc_krylov_primitives_module_ownership_invalid",
                    "The compiler lost its live preallocated module owner.",
                    compile_log=compile_log,
                )
            functions = {
                key: _required_function(
                    runtime, module, symbol, key.replace("_", " "), compile_log
                )
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
        kernel = HipRtcKrylovPrimitivesKernel(
            runtime=runtime,
            module=module,
            functions=functions,
            identity=identity,
            ownership_cell=cleanup_owner._ownership_cell,
        )
        if _handoff is not None:
            _handoff.promote(cleanup_owner, kernel)
        else:
            _transfer_krylov_primitives_module_ownership(cleanup_owner, kernel)
        return kernel
    except BaseException as primary:
        if "kernel" in locals() and _handoff is not None and _handoff.kernel is kernel:
            raise
        with cleanup_owner._ownership_cell.lock:
            if "kernel" in locals() and cleanup_owner._ownership_cell.owner is kernel:
                _reclaim_krylov_primitives_module_ownership(cleanup_owner, kernel)
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
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_symbol_missing",
            f"hipModuleGetFunction failed for fixed {label} symbol "
            f"{symbol}: {runtime.error_string(status)}.",
            compile_log=compile_log,
        )
    return function


def _cleanup_loaded_module(
    cleanup_owner: _HipRtcKrylovPrimitivesModuleCleanupOwner,
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
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_module_cleanup_failed",
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
) -> HipRtcKrylovPrimitivesKernelIdentity:
    initial = HipRtcKrylovPrimitivesKernelIdentity(
        schema_version=HIP_RTC_KRYLOV_PRIMITIVES_IDENTITY_SCHEMA_VERSION,
        abi_version=HIP_RTC_KRYLOV_PRIMITIVES_ABI_VERSION,
        kernel_name=HIP_RTC_KRYLOV_PRIMITIVES_KERNEL_NAME,
        prepare_positive_jacobi_symbol=(HIP_RTC_KRYLOV_PREPARE_POSITIVE_JACOBI_SYMBOL),
        fill_symbol=HIP_RTC_KRYLOV_FILL_SYMBOL,
        affine_symbol=HIP_RTC_KRYLOV_AFFINE_SYMBOL,
        apply_jacobi_symbol=HIP_RTC_KRYLOV_APPLY_JACOBI_SYMBOL,
        dot_stage_symbol=HIP_RTC_KRYLOV_DOT_STAGE_SYMBOL,
        sum_stage_symbol=HIP_RTC_KRYLOV_SUM_STAGE_SYMBOL,
        lassq_stage_symbol=HIP_RTC_KRYLOV_LASSQ_STAGE_SYMBOL,
        lassq_combine_stage_symbol=HIP_RTC_KRYLOV_LASSQ_COMBINE_STAGE_SYMBOL,
        lassq_finalize_symbol=HIP_RTC_KRYLOV_LASSQ_FINALIZE_SYMBOL,
        block_size=HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE,
        reduction_values_per_block=HIP_RTC_KRYLOV_REDUCTION_VALUES_PER_BLOCK,
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
    identity: HipRtcKrylovPrimitivesKernelIdentity,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": {
            "prepare_positive_jacobi": identity.prepare_positive_jacobi_symbol,
            "fill": identity.fill_symbol,
            "affine": identity.affine_symbol,
            "apply_jacobi": identity.apply_jacobi_symbol,
            "dot_stage": identity.dot_stage_symbol,
            "sum_stage": identity.sum_stage_symbol,
            "lassq_stage": identity.lassq_stage_symbol,
            "lassq_combine_stage": identity.lassq_combine_stage_symbol,
            "lassq_finalize": identity.lassq_finalize_symbol,
        },
        "launch_geometry": {
            "block_size": identity.block_size,
            "reduction_values_per_block": identity.reduction_values_per_block,
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
    if type(identity) is not HipRtcKrylovPrimitivesKernelIdentity:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Krylov primitive identity type is invalid.",
        )
    integer_fields = (
        identity.abi_version,
        identity.block_size,
        identity.reduction_values_per_block,
        identity.hiprtc_version_major,
        identity.hiprtc_version_minor,
        identity.code_object_byte_length,
    )
    string_fields = (
        identity.schema_version,
        identity.kernel_name,
        *identity.kernel_symbols,
        identity.source_resource,
        identity.source_sha256,
        identity.architecture,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if (
        any(type(value) is not int for value in integer_fields)
        or any(type(value) is not str for value in string_fields)
        or type(identity._code_object_witness) is not bytes
        or type(identity.compile_options) is not tuple
        or any(type(value) is not str for value in identity.compile_options)
    ):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Krylov primitive identity fields require exact scalar and tuple types.",
        )
    expected_symbols = tuple(symbol for _, symbol in _SYMBOL_ITEMS)
    if (
        identity.schema_version != HIP_RTC_KRYLOV_PRIMITIVES_IDENTITY_SCHEMA_VERSION
        or identity.abi_version != HIP_RTC_KRYLOV_PRIMITIVES_ABI_VERSION
        or identity.kernel_name != HIP_RTC_KRYLOV_PRIMITIVES_KERNEL_NAME
        or identity.kernel_symbols != expected_symbols
        or identity.block_size != HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE
        or identity.reduction_values_per_block
        != HIP_RTC_KRYLOV_REDUCTION_VALUES_PER_BLOCK
        or identity.source_resource != _SOURCE_RESOURCE
    ):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Fixed Krylov primitive ABI identity is invalid.",
        )
    if identity.source_sha256 != _sha256_bytes(_fixed_source()):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Krylov primitive source hash does not match package-owned source.",
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid", exc.message
        ) from exc
    expected_options = (
        f"--offload-arch={identity.architecture}",
        *_FIXED_OPTION_SUFFIX,
    )
    if identity.compile_options != expected_options:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Krylov primitive compile options are not fixed.",
        )
    hashes = (
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Krylov primitive identity has an invalid SHA-256.",
        )
    if (
        len(identity._code_object_witness) != identity.code_object_byte_length
        or _sha256_bytes(identity._code_object_witness) != identity.code_object_sha256
    ):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Krylov primitive code-object witness does not match its identity.",
        )
    if (
        identity.hiprtc_version_major < 0
        or identity.hiprtc_version_minor < 0
        or identity.code_object_byte_length <= 0
    ):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_invalid",
            "Krylov primitive version or code-object length is invalid.",
        )
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_identity_hash_mismatch",
            "Krylov primitive identity hash is invalid.",
        )


def _fixed_source() -> bytes:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_source_missing",
            "The package-owned Krylov primitive source is unavailable: "
            f"{type(exc).__name__}.",
        ) from exc
    signatures = tuple(
        b'extern "C" __global__ void ' + symbol.encode("ascii") + b"("
        for _, symbol in _SYMBOL_ITEMS
    )
    if not source or any(source.count(signature) != 1 for signature in signatures):
        raise HipRtcKrylovPrimitivesError(
            "hip_rtc_krylov_primitives_source_invalid",
            "The package-owned Krylov primitive source must contain all "
            "fixed symbols exactly once.",
        )
    return source


def _positive_int32(value: Any, label: str) -> int:
    if type(value) is not int or not 0 < value <= _INT32_MAX:
        raise _launch_contract_error(f"{label} must be a positive signed int32 value.")
    return value


def _finite_float64(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise _launch_contract_error(
            f"{label} must be an exact int or float convertible to finite float64."
        )
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise _launch_contract_error(
            f"{label} must be convertible to finite float64."
        ) from exc
    if not math.isfinite(converted):
        raise _launch_contract_error(f"{label} must be finite float64.")
    return converted


def _vector_block_count(value_count: int) -> int:
    return (
        value_count + HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE - 1
    ) // HIP_RTC_KRYLOV_PRIMITIVES_BLOCK_SIZE


def _pointer_arguments(values: tuple[tuple[str, Any], ...]) -> tuple[int, ...]:
    return tuple(_runtime_pointer(value, label) for label, value in values)


def _runtime_pointer(value: Any, label: str) -> int:
    try:
        pointer = _pointer_integer(value, label)
    except HipRtcError as exc:
        raise _launch_contract_error(exc.message) from exc
    if pointer > _UINTPTR_MAX:
        raise _launch_contract_error(f"{label} exceeds the native uintptr capacity.")
    packed = ctypes.c_void_p(pointer)
    if packed.value != pointer:
        raise _launch_contract_error(
            f"{label} does not round-trip through ctypes.c_void_p."
        )
    return pointer


def _launch_contract_error(message: str) -> HipRtcKrylovPrimitivesError:
    return HipRtcKrylovPrimitivesError(
        "hip_rtc_krylov_primitives_launch_contract_invalid", message
    )
