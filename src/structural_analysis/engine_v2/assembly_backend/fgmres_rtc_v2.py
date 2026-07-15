"""HIPRTC owner for the fixed-source FGMRES recurrence-v2 column-zero slice.

The single code object owned here contains the four symbols reserved by the
recurrence-v2 plan.  It implements initialization, initial ``x``/``b-Ax``
formation and dual convergence gate, then the first restart/column-zero path
through right-Jacobi, Arnoldi SpMV, both device-gated DGKS paths, ``h_next``,
``V1`` normalization, the first Givens update, back substitution, trial-vector
construction, solution-update acceptance, candidate SpMV, in-place true
residual formation, its L2/Linf metrics, and trial/committed solution scale
metrics and the raw four-launch checkpoint decide/preflight/commit/finalize
slice.  A
live parent-integrated solver context remains outside this low-level owner;
the caller-attested exclusive checkpoint transaction wrapper lives in
``fgmres_context_v2``.

The owner compiles, loads and launches package-owned device code.  Its private
checkpoint lease can observe an exact-runtime stream fence and atomically
consume the corresponding pending reservations; it never allocates solver
buffers, copies values, or selects a fallback implementation.
"""

from __future__ import annotations

import ctypes
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field, replace
import math
from pathlib import Path
import re
import threading
from typing import Any
import weakref

from structural_analysis.engine_v2.backends.hip.native import LoadedHipRuntime
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

from .fgmres_plan import (
    HIP_FGMRES_MAX_ITERATIONS,
    HIP_FGMRES_MAX_RESTART_DIMENSION,
)
from .fgmres_recurrence_plan_v2 import (
    HIP_FGMRES_CONTROL_ABI_VERSION_V2,
    HIP_FGMRES_CONTROL_STATE_BYTES_V2,
    HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
    hip_fgmres_control_state_abi_payload_v2,
    hip_fgmres_first_column_candidate_preparation_schedule_payload_v2,
    hip_fgmres_first_column_candidate_residual_schedule_payload_v2,
    hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2,
    hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2,
    hip_fgmres_first_column_completion_schedule_payload_v2,
    hip_fgmres_first_column_partial_schedule_payload_v2,
    hip_fgmres_first_column_predecessor_validation_schedule_payload_v2,
    hip_fgmres_recurrence_kernel_abi_payload_v2,
    hip_fgmres_solve_record_abi_payload_v2,
)
from .fgmres_rtc_launch_fence_ledger_v1 import (
    _RTC_LAUNCH_FENCE_LEDGER_SNAPSHOT_MINT_V1,
    _HipFgmresRtcLaunchFenceLedgerStateV1,
    _fallback_descriptor_hash_v1,
    _fence_descriptor_hash_v1,
)


HIP_RTC_FGMRES_V2_IDENTITY_SCHEMA_VERSION = (
    "structural-analysis-hip-rtc-fgmres-kernel-identity.v2"
)
HIP_RTC_FGMRES_V2_ABI_VERSION = 2
HIP_RTC_FGMRES_V2_KERNEL_NAME = "engine_v2_fgmres_v2"
HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE = 1
HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE = 256
HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK = 512
HIP_RTC_FGMRES_V2_CONTROL_STATE_BYTES = HIP_FGMRES_CONTROL_STATE_BYTES_V2

HIP_RTC_FGMRES_V2_CONTROL_SYMBOL = "engine_v2_fgmres_control_v2"
HIP_RTC_FGMRES_V2_VECTOR_SYMBOL = "engine_v2_fgmres_vector_v2"
HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL = "engine_v2_fgmres_csr_spmv_indexed_v2"
HIP_RTC_FGMRES_V2_REDUCE_SYMBOL = "engine_v2_fgmres_reduce_v2"

_SOURCE_RESOURCE = "kernels/engine_v2_fgmres_v2.hip.cpp"
_SOURCE_PATH = Path(__file__).with_name("kernels") / Path(_SOURCE_RESOURCE).name
_FIXED_OPTION_SUFFIX = ("-O3", "-std=c++17", "-ffp-contract=off")
_INT32_MAX = (1 << 31) - 1
_UINTPTR_MAX = (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1
_HIP_ERROR_NOT_READY = 600
_KERNEL_OWNER_MINT = object()

_SYMBOL_ITEMS = (
    ("control", HIP_RTC_FGMRES_V2_CONTROL_SYMBOL),
    ("vector", HIP_RTC_FGMRES_V2_VECTOR_SYMBOL),
    ("csr_spmv_indexed", HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL),
    ("reduce", HIP_RTC_FGMRES_V2_REDUCE_SYMBOL),
)


class _HipRtcFgmresV2ModuleOwnershipCell:
    """Single mutable authority cell for one native module handle."""

    __slots__ = (
        "module",
        "owner",
        "preowner",
        "lock",
        "unload_disposition",
    )

    def __init__(self, module: ctypes.c_void_p) -> None:
        if type(module) is not ctypes.c_void_p:
            raise ValueError("module ownership cell requires an exact module box")
        self.module = module
        self.owner: _HipRtcFgmresV2ModuleCleanupOwner | HipRtcFgmresV2Kernel | None = (
            None
        )
        self.preowner: _HipRtcFgmresV2ModuleCleanupOwner | None = None
        self.lock = threading.RLock()
        self.unload_disposition = "live"


class _HipRtcFgmresV2KernelHandoff:
    """Strong evolving module/kernel owner referenced weakly by its route."""

    __slots__ = ("_cell", "_lock", "_publication_state", "__weakref__")

    def __init__(self) -> None:
        self._cell: _HipRtcFgmresV2ModuleOwnershipCell | None = None
        self._lock = threading.RLock()
        self._publication_state = "empty"

    @property
    def kernel(
        self,
    ) -> _HipRtcFgmresV2ModuleCleanupOwner | HipRtcFgmresV2Kernel | None:
        with self._lock:
            cell = self._cell
            if self._publication_state != "published" or cell is None:
                return None
            with cell.lock:
                owner = cell.owner
                if type(owner) is _HipRtcFgmresV2ModuleCleanupOwner:
                    return (
                        owner
                        if owner.owns_module
                        or (
                            cell.owner is owner
                            and cell.unload_disposition == "terminal"
                        )
                        else None
                    )
                return owner if type(owner) is HipRtcFgmresV2Kernel else None

    @property
    def occupied(self) -> bool:
        with self._lock:
            return self._publication_state != "empty"

    def publish_module_owner(
        self,
        owner: _HipRtcFgmresV2ModuleCleanupOwner,
    ) -> None:
        cell = getattr(owner, "_ownership_cell", None)
        with self._lock:
            if self._publication_state != "empty" or self._cell is not None:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_kernel_handoff_invalid",
                    "The handoff accepts one exact live module owner before native load.",
                )
            self._publication_state = "reserved"
            try:
                if type(cell) is not _HipRtcFgmresV2ModuleOwnershipCell:
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_kernel_handoff_invalid",
                        "The handoff requires one exact module ownership cell.",
                    )
                with cell.lock:
                    if (
                        type(owner) is not _HipRtcFgmresV2ModuleCleanupOwner
                        or cell.owner is not owner
                        or cell.preowner is not owner
                        or cell.unload_disposition != "live"
                    ):
                        raise HipRtcFgmresV2Error(
                            "hip_rtc_fgmres_v2_kernel_handoff_invalid",
                            "The handoff accepts one exact live module owner before native load.",
                        )
                    self._cell = cell
                    self._publication_state = "published"
            except BaseException:
                if self._publication_state == "reserved":
                    self._publication_state = "spent"
                raise

    def promote(
        self,
        module_owner: _HipRtcFgmresV2ModuleCleanupOwner,
        kernel: HipRtcFgmresV2Kernel,
    ) -> None:
        with self._lock:
            cell = self._cell
            if (
                self._publication_state != "published"
                or type(cell) is not _HipRtcFgmresV2ModuleOwnershipCell
            ):
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_kernel_handoff_invalid",
                    "The handoff lost its exact published ownership cell.",
                )
            with cell.lock:
                if (
                    type(module_owner) is not _HipRtcFgmresV2ModuleCleanupOwner
                    or type(kernel) is not HipRtcFgmresV2Kernel
                    or module_owner._ownership_cell is not cell
                    or kernel._ownership_cell is not cell
                    or cell.owner is not module_owner
                ):
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_kernel_handoff_invalid",
                        "Only the published module owner can promote its exact kernel.",
                    )
                _transfer_fgmres_v2_module_ownership(module_owner, kernel)


def _transfer_fgmres_v2_module_ownership(
    module_owner: _HipRtcFgmresV2ModuleCleanupOwner,
    kernel: HipRtcFgmresV2Kernel,
) -> None:
    """Atomically replace the preowner with its fully bound kernel."""

    cell = module_owner._ownership_cell
    if type(cell) is not _HipRtcFgmresV2ModuleOwnershipCell:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_module_ownership_invalid",
            "Module transfer requires an exact ownership cell.",
        )
    with cell.lock:
        if (
            kernel._ownership_cell is not cell
            or cell.owner is not module_owner
            or cell.unload_disposition != "live"
            or not cell.module.value
        ):
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_module_ownership_invalid",
                "Only a live loaded preowner can transfer module authority.",
            )
        cell.owner = kernel


def _reclaim_fgmres_v2_module_ownership(
    module_owner: _HipRtcFgmresV2ModuleCleanupOwner,
    kernel: HipRtcFgmresV2Kernel,
) -> None:
    """Atomically return an unpublished kernel's authority to its preowner."""

    cell = kernel._ownership_cell
    with cell.lock:
        if (
            type(module_owner) is not _HipRtcFgmresV2ModuleCleanupOwner
            or module_owner._ownership_cell is not cell
            or cell.preowner is not module_owner
            or cell.owner is not kernel
            or cell.unload_disposition != "live"
        ):
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_module_ownership_invalid",
                "Only the exact live unpublished kernel can return module authority.",
            )
        cell.owner = module_owner
    with _KERNEL_BINDING_LOCK:
        _KERNEL_BINDINGS.pop(kernel, None)


class _HipRtcFgmresV2KernelHandoffFrame:
    """One-shot weak task-local route; a stale frame owns no native resource."""

    __slots__ = ("_target_refs",)

    def __init__(self, target: _HipRtcFgmresV2KernelHandoff) -> None:
        self._target_refs = [weakref.ref(target)]

    def claim(self) -> _HipRtcFgmresV2KernelHandoff | None:
        try:
            target_ref = self._target_refs.pop()
        except IndexError:
            return None
        return target_ref()

    def disarm(self) -> None:
        self._target_refs.clear()


_KERNEL_HANDOFF: ContextVar[_HipRtcFgmresV2KernelHandoffFrame | None] = ContextVar(
    "engine_v2_fgmres_v2_kernel_handoff",
    default=None,
)


def _control_abi() -> dict[str, Any]:
    return hip_fgmres_control_state_abi_payload_v2()


def _record_abi() -> dict[str, Any]:
    return hip_fgmres_solve_record_abi_payload_v2()


def _kernel_abi() -> dict[str, Any]:
    return hip_fgmres_recurrence_kernel_abi_payload_v2()


def _validated_completion_schedule(
    interface: dict[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    """Cross-check the owner formulas against the combined canonical ABI."""

    try:
        partial = hip_fgmres_first_column_partial_schedule_payload_v2()
        completion = hip_fgmres_first_column_completion_schedule_payload_v2()
        launches = completion["launches"]
        coordinates = tuple(
            (
                row["name"],
                row["symbol"],
                row.get("first_mode", row.get("mode")),
                row.get("combine_mode"),
                row["expected_schedule_epoch"],
                row.get("expected_reduction_epoch"),
                row["expected_restart"],
                row["expected_column"],
                row.get("logical_index"),
                row.get("row_index"),
                row.get("pass_index"),
                row.get("gate"),
                row.get("intermediate_target"),
                row.get("final_target"),
            )
            for row in launches
        )
        expected_coordinates = (
            (
                "REDUCE_DOT_SECOND_PASS_ROW0",
                HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                "DOT_W_VI",
                "COMBINE_SUM",
                "16+q",
                "q=7*S..8*S-1",
                1,
                0,
                0,
                None,
                None,
                None,
                "NONE",
                "DOT",
            ),
            (
                "CONTROL_DOT_ACCEPT_ROW0_PASS1",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "DOT_ACCEPT",
                None,
                "16+8*S",
                None,
                1,
                0,
                None,
                0,
                1,
                None,
                None,
                None,
            ),
            (
                "VECTOR_MGS_SUBTRACT_ROW0_PASS1",
                HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                "MGS_SUBTRACT_INDEXED",
                None,
                "17+8*S",
                None,
                1,
                0,
                0,
                None,
                None,
                "DGKS_SECOND_PASS",
                None,
                None,
            ),
            (
                "REDUCE_H_NEXT",
                HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                "LASSQ_WORK_W",
                "COMBINE_LASSQ",
                "18+q",
                "q=8*S..9*S-1",
                1,
                0,
                0,
                None,
                None,
                None,
                "NONE",
                "H_NEXT",
            ),
            (
                "VECTOR_NORMALIZE_V1",
                HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                "NORMALIZE_V_NEXT",
                None,
                "18+9*S",
                None,
                1,
                0,
                1,
                None,
                None,
                "ACTIVE",
                None,
                None,
            ),
            (
                "CONTROL_ARNOLDI_GIVENS_COLUMN0",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "ARNOLDI_GIVENS",
                None,
                "19+9*S",
                None,
                1,
                0,
                None,
                -1,
                -1,
                None,
                None,
                None,
            ),
        )
        valid = (
            type(interface) is dict
            and interface["first_column_partial_schedule"] == partial
            and interface["first_column_partial_schedule_hash"]
            == canonical_hash(partial)
            and interface["first_column_completion_schedule"] == completion
            and interface["first_column_completion_schedule_hash"]
            == canonical_hash(completion)
            and completion["predecessor_contract"]["schedule_hash"]
            == canonical_hash(partial)
            and coordinates == expected_coordinates
            and completion["gated_second_pass_contract"][
                "host_schedule_is_flag_independent"
            ]
            is True
            and completion["end_state"]["schedule_epoch"] == "20+9*S"
            and completion["end_state"]["reduction_epoch"] == "9*S"
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise HipRtcFgmresV2Error(
            code,
            "FGMRES v2 column-zero completion schedule is not the exact "
            "schedule bound by the combined recurrence interface.",
        )
    return completion


def _validated_candidate_preparation_schedule(
    interface: dict[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    """Cross-check owner formulas against the candidate-preparation ABI."""

    try:
        completion = _validated_completion_schedule(interface, code=code)
        preparation = (
            hip_fgmres_first_column_candidate_preparation_schedule_payload_v2()
        )
        coordinates = tuple(
            (
                row["name"],
                row["symbol"],
                row.get("first_mode", row.get("mode")),
                row.get("combine_mode"),
                row["expected_schedule_epoch"],
                row.get("expected_reduction_epoch"),
                row["expected_restart"],
                row["expected_column"],
                row.get("logical_index"),
                row.get("row_index"),
                row.get("pass_index"),
                row.get("gate"),
                row.get("intermediate_target"),
                row.get("final_target"),
            )
            for row in preparation["launches"]
        )
        expected_coordinates = (
            (
                "CONTROL_BACKSUBSTITUTE_COLUMN0",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "BACKSUBSTITUTE",
                None,
                "20+9*S",
                None,
                1,
                0,
                None,
                -1,
                -1,
                None,
                None,
                None,
            ),
            (
                "VECTOR_BUILD_TRIAL_X_COLUMN0",
                HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                "BUILD_TRIAL_X",
                None,
                "21+9*S",
                None,
                1,
                0,
                0,
                None,
                None,
                "CANDIDATE_REQUIRED",
                None,
                None,
            ),
            (
                "REDUCE_SOLUTION_UPDATE_L2_COLUMN0",
                HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                "LASSQ_WORK_W_MINUS_X",
                "COMBINE_LASSQ",
                "22+q",
                "q=9*S..10*S-1",
                1,
                0,
                0,
                None,
                None,
                None,
                "NONE",
                "UPDATE_L2",
            ),
            (
                "CONTROL_VECTOR_ACCEPT_TRIAL_COLUMN0",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "VECTOR_ACCEPT",
                None,
                "22+10*S",
                None,
                1,
                0,
                None,
                -1,
                -1,
                None,
                None,
                None,
            ),
        )
        valid = (
            type(interface) is dict
            and interface["first_column_candidate_preparation_schedule"] == preparation
            and interface["first_column_candidate_preparation_schedule_hash"]
            == canonical_hash(preparation)
            and preparation["predecessor_contract"]["schedule_hash"]
            == canonical_hash(completion)
            and coordinates == expected_coordinates
            and preparation["gated_preparation_contract"][
                "host_schedule_is_candidate_flag_independent"
            ]
            is True
            and preparation["gated_preparation_contract"][
                "all_four_launch_groups_submitted_for_both_candidate_values"
            ]
            is True
            and preparation["reduction_validity_contract"]["target_code"]
            == {"UPDATE_L2": 11}
            and preparation["reduction_validity_contract"]["valid_bit"]
            == {"UPDATE_L2": 10}
            and preparation["end_state"]["schedule_epoch"] == "23+10*S"
            and preparation["end_state"]["reduction_epoch"] == "10*S"
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise HipRtcFgmresV2Error(
            code,
            "FGMRES v2 column-zero candidate-preparation schedule is not "
            "the exact schedule bound by the combined recurrence interface.",
        )
    return preparation


def _validated_candidate_residual_schedule(
    interface: dict[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    """Cross-check owner formulas against the candidate-residual ABI."""

    try:
        preparation = _validated_candidate_preparation_schedule(interface, code=code)
        residual = hip_fgmres_first_column_candidate_residual_schedule_payload_v2()
        coordinates = tuple(
            (
                row["name"],
                row["symbol"],
                row.get("first_mode", row.get("mode")),
                row.get("combine_mode"),
                row["expected_schedule_epoch"],
                row.get("expected_reduction_epoch"),
                row["expected_restart"],
                row["expected_column"],
                row.get("logical_index"),
                row.get("row_index"),
                row.get("pass_index"),
                row.get("gate"),
                row.get("intermediate_target"),
                row.get("final_target"),
            )
            for row in residual["launches"]
        )
        expected_coordinates = (
            (
                "SPMV_CANDIDATE_COLUMN0",
                HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL,
                "CANDIDATE",
                None,
                "23+10*S",
                None,
                1,
                0,
                "M",
                None,
                None,
                None,
                None,
                None,
            ),
            (
                "CONTROL_OPERATOR_ACCEPT_CANDIDATE_COLUMN0",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "OPERATOR_ACCEPT",
                None,
                "24+10*S",
                None,
                1,
                0,
                None,
                -1,
                -1,
                None,
                None,
                None,
            ),
            (
                "VECTOR_FORM_CANDIDATE_RESIDUAL_COLUMN0",
                HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                "FORM_CANDIDATE_RESIDUAL",
                None,
                "25+10*S",
                None,
                1,
                0,
                "M",
                None,
                None,
                "CANDIDATE_REQUIRED",
                None,
                None,
            ),
            (
                "REDUCE_CANDIDATE_L2_COLUMN0",
                HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                "LASSQ_V_M",
                "COMBINE_LASSQ",
                "26+q",
                "q=10*S..11*S-1",
                1,
                0,
                "M",
                None,
                None,
                None,
                "NONE",
                "CANDIDATE_L2",
            ),
            (
                "REDUCE_CANDIDATE_LINF_COLUMN0",
                HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                "LINF_V_M",
                "COMBINE_MAX",
                "26+q",
                "q=11*S..12*S-1",
                1,
                0,
                "M",
                None,
                None,
                None,
                "NONE",
                "CANDIDATE_LINF",
            ),
        )
        valid = (
            type(interface) is dict
            and interface["first_column_candidate_residual_schedule"] == residual
            and interface["first_column_candidate_residual_schedule_hash"]
            == canonical_hash(residual)
            and residual["predecessor_contract"]["schedule_hash"]
            == canonical_hash(preparation)
            and coordinates == expected_coordinates
            and residual["active_predicate"]["host_submission_depends_on_predicate"]
            is False
            and residual["always_submit_gated_contract"][
                "all_five_launch_groups_submitted_for_all_gate_values"
            ]
            is True
            and residual["reduction_validity_contract"]["target_codes"]
            == {"CANDIDATE_L2": 9, "CANDIDATE_LINF": 10}
            and residual["reduction_validity_contract"]["valid_bits"]
            == {"CANDIDATE_L2": 8, "CANDIDATE_LINF": 9}
            and residual["numeric_policy_contract"][
                "represented_fp64_final_l2_overflow_policy"
            ]
            == "terminal_nonfinite_arithmetic_failure"
            and residual["numeric_policy_contract"][
                "represented_fp64_final_l2_overflow_exact_cpu_parity_claimed"
            ]
            is False
            and residual["end_state"]["schedule_epoch"] == "26+12*S"
            and residual["end_state"]["reduction_epoch"] == "12*S"
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise HipRtcFgmresV2Error(
            code,
            "FGMRES v2 column-zero candidate-residual schedule is not the "
            "exact schedule bound by the combined recurrence interface.",
        )
    return residual


def _validated_candidate_scale_metrics_schedule(
    interface: dict[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    """Cross-check owner formulas against the candidate-scale ABI."""

    try:
        residual = _validated_candidate_residual_schedule(interface, code=code)
        scale = hip_fgmres_first_column_candidate_scale_metrics_schedule_payload_v2()
        coordinates = tuple(
            (
                row["name"],
                row["symbol"],
                row["first_mode"],
                row["combine_mode"],
                row["expected_schedule_epoch"],
                row["expected_reduction_epoch"],
                row["expected_restart"],
                row["expected_column"],
                row["logical_index"],
                row["numeric_gate"],
                row["intermediate_target"],
                row["final_target"],
            )
            for row in scale["launches"]
        )
        expected_coordinates = (
            (
                "REDUCE_TRIAL_X_L2_COLUMN0",
                HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                "LASSQ_WORK_W",
                "COMBINE_LASSQ",
                "26+q",
                "q=12*S..13*S-1",
                1,
                0,
                0,
                "scale_metrics_required",
                "NONE",
                "TRIAL_X_L2",
            ),
            (
                "REDUCE_COMMITTED_X_L2_COLUMN0",
                HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                "LASSQ_SOLUTION_X",
                "COMBINE_LASSQ",
                "26+q",
                "q=13*S..14*S-1",
                1,
                0,
                0,
                "scale_metrics_required",
                "NONE",
                "COMMITTED_X_L2",
            ),
        )
        valid = (
            type(interface) is dict
            and interface["first_column_candidate_scale_metrics_schedule"] == scale
            and interface["first_column_candidate_scale_metrics_schedule_hash"]
            == canonical_hash(scale)
            and scale["predecessor_contract"]["schedule_hash"]
            == canonical_hash(residual)
            and coordinates == expected_coordinates
            and scale["scale_metrics_required_contract"][
                "host_submission_depends_on_predicate"
            ]
            is False
            and scale["always_submit_gated_contract"][
                "both_launch_groups_submitted_for_all_predicate_values"
            ]
            is True
            and scale["target_lifetime_contract"]["existing_consumer_metadata_modified"]
            is False
            and scale["reduction_validity_contract"]["target_codes"]
            == {"TRIAL_X_L2": 13, "COMMITTED_X_L2": 12}
            and scale["end_state"]["schedule_epoch"] == "26+14*S"
            and scale["end_state"]["reduction_epoch"] == "14*S"
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise HipRtcFgmresV2Error(
            code,
            "FGMRES v2 column-zero candidate-scale schedule is not the exact "
            "schedule bound by the combined recurrence interface.",
        )
    return scale


def _validated_checkpoint_transaction_schedule(
    interface: dict[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    """Cross-check owner coordinates against the checkpoint transaction ABI."""

    try:
        scale = _validated_candidate_scale_metrics_schedule(interface, code=code)
        transaction = (
            hip_fgmres_first_column_checkpoint_transaction_schedule_payload_v2()
        )
        launches = transaction["launches"]
        coordinates = (
            (
                launches[0]["name"],
                launches[0]["symbol"],
                launches[0]["control_mode"],
                launches[0]["control_mode_code"],
                launches[0]["expected_schedule_epoch"],
                launches[0]["required_reduction_epoch"],
                launches[0]["expected_restart"],
                launches[0]["expected_column"],
                launches[0]["row_index"],
                launches[0]["pass_index"],
            ),
            (
                launches[1]["name"],
                launches[1]["symbol"],
                launches[1]["vector_mode"],
                launches[1]["vector_mode_code"],
                launches[1]["vector_gate"],
                launches[1]["vector_gate_code"],
                launches[1]["expected_schedule_epoch"],
                launches[1]["required_reduction_epoch"],
                launches[1]["expected_restart"],
                launches[1]["expected_column"],
                launches[1]["logical_index"],
            ),
            (
                launches[2]["name"],
                launches[2]["symbol"],
                launches[2]["vector_mode"],
                launches[2]["vector_mode_code"],
                launches[2]["vector_gate"],
                launches[2]["vector_gate_code"],
                launches[2]["expected_schedule_epoch"],
                launches[2]["required_reduction_epoch"],
                launches[2]["expected_restart"],
                launches[2]["expected_column"],
                launches[2]["logical_index"],
            ),
            (
                launches[3]["name"],
                launches[3]["symbol"],
                launches[3]["control_mode"],
                launches[3]["control_mode_code"],
                launches[3]["expected_schedule_epoch"],
                launches[3]["required_reduction_epoch"],
                launches[3]["expected_restart"],
                launches[3]["expected_column"],
                launches[3]["row_index"],
                launches[3]["pass_index"],
            ),
        )
        expected_coordinates = (
            (
                "CHECKPOINT_DECIDE_COLUMN0",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "CHECKPOINT_DECIDE",
                11,
                "26+14*S",
                "14*S",
                1,
                0,
                -1,
                -1,
            ),
            (
                "PREFLIGHT_COMMIT_SOURCE_COLUMN0",
                HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                "PREFLIGHT_COMMIT_SOURCE",
                9,
                "COMMIT_REQUIRED",
                4,
                "27+14*S",
                "14*S",
                1,
                0,
                "M",
            ),
            (
                "COMMIT_CHECKPOINT_COLUMN0",
                HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                "COMMIT_CHECKPOINT",
                8,
                "COMMIT_REQUIRED",
                4,
                "27+14*S",
                "14*S",
                1,
                0,
                "M",
            ),
            (
                "CHECKPOINT_FINALIZE_COLUMN0",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "CHECKPOINT_FINALIZE",
                12,
                "28+14*S",
                "14*S",
                1,
                0,
                -1,
                -1,
            ),
        )
        valid = (
            type(interface) is dict
            and interface["first_column_checkpoint_transaction_schedule"] == transaction
            and interface["first_column_checkpoint_transaction_schedule_hash"]
            == canonical_hash(transaction)
            and transaction["predecessor_contract"]["schedule_hash"]
            == canonical_hash(scale)
            and coordinates == expected_coordinates
            and transaction["fixed_submission_contract"][
                "four_launches_always_submitted"
            ]
            is True
            and transaction["fixed_submission_contract"][
                "host_submission_depends_on_candidate_or_outcome"
            ]
            is False
            and transaction["scope"]["final_guard_included"] is False
            and transaction["pointer_alias_contract"]["host_shifted_pointer_allowed"]
            is False
            and transaction["pointer_alias_contract"]["forbidden_exact_alias_pairs"]
            == [
                ["work_w_base", "solution_x_base"],
                ["basis_v_base", "true_residual_base"],
                ["work_w_base", "true_residual_base"],
                ["basis_v_base", "solution_x_base"],
                ["solution_x_base", "true_residual_base"],
            ]
            and transaction["fixed_submission_contract"][
                "successful_end_schedule_epoch"
            ]
            == "29+14*S"
            and transaction["fixed_submission_contract"][
                "successful_end_reduction_epoch"
            ]
            == "14*S"
        )
    except (IndexError, KeyError, TypeError):
        valid = False
    if not valid:
        raise HipRtcFgmresV2Error(
            code,
            "FGMRES v2 column-zero checkpoint transaction is not the exact "
            "schedule bound by the combined recurrence interface.",
        )
    return transaction


def _validated_predecessor_validation_schedule(
    interface: dict[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    """Cross-check the non-advancing first-column device seal ABI."""

    try:
        scale = _validated_candidate_scale_metrics_schedule(interface, code=code)
        validation = (
            hip_fgmres_first_column_predecessor_validation_schedule_payload_v2()
        )
        launch = validation["launch"]
        valid = (
            type(interface) is dict
            and interface["first_column_predecessor_validation_schedule"] == validation
            and interface["first_column_predecessor_validation_schedule_hash"]
            == canonical_hash(validation)
            and validation["predecessor_contract"]["schedule_hash"]
            == canonical_hash(scale)
            and (
                launch["name"],
                launch["symbol"],
                launch["control_mode"],
                launch["control_mode_code"],
                launch["expected_schedule_epoch"],
                launch["required_reduction_epoch"],
                launch["expected_restart"],
                launch["expected_column"],
                launch["row_index"],
                launch["pass_index"],
            )
            == (
                "PREDECESSOR_VALIDATE_COLUMN0",
                HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                "PREDECESSOR_VALIDATE",
                14,
                "26+14*S",
                "14*S",
                1,
                0,
                -1,
                -1,
            )
            and validation["predecessor_contract"]["admitted_reduction_valid_masks"]
            == [0, 1792, 7936]
            and validation["seal_contract"]["success_advances_schedule_epoch"] is False
            and validation["seal_contract"]["success_advances_reduction_epoch"] is False
            and validation["host_observation_contract"]["actual_mask_host_observed"]
            is False
        )
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise HipRtcFgmresV2Error(
            code,
            "FGMRES v2 first-column predecessor validator is not the exact "
            "device seal bound by the combined recurrence interface.",
        )
    return validation


_CONTROL_MODES = _control_abi()["control_mode_codes"]
_VECTOR_MODES = _control_abi()["vector_mode_codes"]
_VECTOR_GATES = _control_abi()["vector_gate_codes"]
_SPMV_MODES = _control_abi()["spmv_mode_codes"]
_REDUCTION_MODES = _control_abi()["reduction_mode_codes"]
_REDUCTION_TARGETS = _control_abi()["reduction_target_codes"]

_IMPLEMENTED_CONTROL_MODES = frozenset(
    _CONTROL_MODES[name]
    for name in (
        "INIT",
        "BIND_RHS",
        "INITIAL_GATE",
        "RESTART_BEGIN",
        "PRECONDITION_ACCEPT",
        "OPERATOR_ACCEPT",
        "DOT_ACCEPT",
        "DGKS_DECIDE",
        "ARNOLDI_GIVENS",
        "BACKSUBSTITUTE",
        "VECTOR_ACCEPT",
        "CHECKPOINT_DECIDE",
        "CHECKPOINT_FINALIZE",
        "FINAL_GUARD",
        "PREDECESSOR_VALIDATE",
    )
)
_IMPLEMENTED_VECTOR_MODES = frozenset(
    _VECTOR_MODES[name]
    for name in (
        "COPY_INITIAL_X",
        "FORM_INITIAL_RESIDUAL",
        "NORMALIZE_V0",
        "APPLY_JACOBI_INDEXED",
        "MGS_SUBTRACT_INDEXED",
        "NORMALIZE_V_NEXT",
        "BUILD_TRIAL_X",
        "FORM_CANDIDATE_RESIDUAL",
        "COMMIT_CHECKPOINT",
        "PREFLIGHT_COMMIT_SOURCE",
    )
)
_IMPLEMENTED_SPMV_MODES = frozenset(
    _SPMV_MODES[name] for name in ("INITIAL", "ARNOLDI", "CANDIDATE")
)
_IMPLEMENTED_REDUCTION_MODES = frozenset(
    _REDUCTION_MODES[name]
    for name in (
        "LASSQ_LOAD",
        "LASSQ_TRUE_RESIDUAL",
        "LASSQ_WORK_W",
        "LASSQ_V_M",
        "LASSQ_WORK_W_MINUS_X",
        "LASSQ_SOLUTION_X",
        "DOT_W_VI",
        "LINF_LOAD",
        "LINF_TRUE_RESIDUAL",
        "LINF_V_M",
        "COMBINE_SUM",
        "COMBINE_LASSQ",
        "COMBINE_MAX",
    )
)
_L2_TARGETS = frozenset(
    _REDUCTION_TARGETS[name]
    for name in (
        "RHS_L2",
        "INITIAL_L2",
        "WORK_BEFORE",
        "AFTER_FIRST",
        "H_NEXT",
        "CANDIDATE_L2",
        "UPDATE_L2",
        "COMMITTED_X_L2",
        "TRIAL_X_L2",
    )
)
_LINF_TARGETS = frozenset(
    _REDUCTION_TARGETS[name] for name in ("RHS_LINF", "INITIAL_LINF", "CANDIDATE_LINF")
)
_DOT_TARGETS = frozenset({_REDUCTION_TARGETS["DOT"]})
_IMPLEMENTED_REDUCTION_TARGETS = frozenset(
    _REDUCTION_TARGETS[name]
    for name in (
        "NONE",
        "DOT",
        "RHS_L2",
        "RHS_LINF",
        "INITIAL_L2",
        "INITIAL_LINF",
        "WORK_BEFORE",
        "AFTER_FIRST",
        "H_NEXT",
        "CANDIDATE_L2",
        "CANDIDATE_LINF",
        "UPDATE_L2",
        "COMMITTED_X_L2",
        "TRIAL_X_L2",
    )
)


class HipRtcFgmresV2Error(HipRtcError):
    """Stable fail-closed error for the recurrence-v2 HIPRTC owner."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        compile_log: str = "",
        cleanup_owner: _HipRtcFgmresV2ModuleCleanupOwner | None = None,
        launch_disposition: str | None = None,
    ) -> None:
        if cleanup_owner is not None and type(cleanup_owner) is not (
            _HipRtcFgmresV2ModuleCleanupOwner
        ):
            raise TypeError("cleanup_owner has an invalid owner type")
        self.cleanup_owner = cleanup_owner
        if launch_disposition not in (
            None,
            "not_attempted",
            "rejected",
            "ambiguous",
        ):
            raise ValueError("launch_disposition is invalid")
        self.launch_disposition = launch_disposition
        super().__init__(code, message, compile_log=compile_log)


class _HipRtcFgmresV2ModuleCleanupOwner:
    """Persistent owner for a loaded v2 module after eager cleanup failure."""

    __slots__ = (
        "_runtime",
        "_module",
        "_ownership_cell",
        "_closed",
    )

    def __init__(self, runtime: _RuntimeModuleApi, module: ctypes.c_void_p) -> None:
        if not module.value:
            raise ValueError("cleanup owner requires a loaded module")
        cell = _HipRtcFgmresV2ModuleOwnershipCell(module)
        self._runtime = runtime
        self._module = module
        self._ownership_cell = cell
        self._closed = False
        cell.preowner = self
        cell.owner = self

    @classmethod
    def _preallocated(
        cls,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
    ) -> _HipRtcFgmresV2ModuleCleanupOwner:
        if type(module) is not ctypes.c_void_p or module.value:
            raise ValueError("preallocated cleanup owner requires an empty module box")
        cell = _HipRtcFgmresV2ModuleOwnershipCell(module)
        owner = object.__new__(cls)
        owner._runtime = runtime
        owner._module = module
        owner._ownership_cell = cell
        owner._closed = False
        cell.preowner = owner
        cell.owner = owner
        return owner

    @property
    def closed(self) -> bool:
        with self._ownership_cell.lock:
            return self._closed

    @property
    def _unload_disposition(self) -> str:
        return self._ownership_cell.unload_disposition

    @_unload_disposition.setter
    def _unload_disposition(self, value: str) -> None:
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
        cell = self._ownership_cell
        with cell.lock:
            if self._closed and cell.owner is not self:
                return
            if cell.owner is not self:
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
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_module_cleanup_outcome_uncertain",
                    "A prior hipModuleUnload cleanup outcome is uncertain; the module handle will not be retried.",
                    cleanup_owner=self,
                )
            status: int | None = None
            self._unload_disposition = "unload_call_inflight"
            try:
                status = int(self._runtime.unload(self._module))
                if status != 0:
                    self._unload_disposition = "live"
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_module_cleanup_failed",
                        "hipModuleUnload cleanup retry failed: "
                        f"{self._runtime.error_string(status)}.",
                        cleanup_owner=self,
                    )
                self._unload_disposition = "external_unload_succeeded"
            except HipRtcFgmresV2Error:
                raise
            except Exception as exc:
                self._unload_disposition = (
                    "external_unload_succeeded"
                    if status == 0
                    else ("live" if status is not None else "unload_outcome_uncertain")
                )
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_module_cleanup_failed",
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
            if cell.owner is not self:
                return
            self._module.value = None
            cell.preowner = None
            self._unload_disposition = "terminal"
            self._closed = True
            cell.owner = None


@dataclass(frozen=True, slots=True)
class HipRtcFgmresV2KernelIdentity:
    """Handle-free identity of one fixed four-symbol v2 code object."""

    schema_version: str
    abi_version: int
    recurrence_abi_version: int
    control_abi_version: int
    kernel_name: str
    kernel_symbols: tuple[str, ...]
    control_block_size: int
    vector_block_size: int
    reduction_values_per_block: int
    control_state_abi_hash: str
    solve_record_abi_hash: str
    kernel_interface_hash: str
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

    def to_dict(self) -> dict[str, Any]:
        _validate_identity(self)
        return _identity_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class FgmresV2InitialReductionLaunch:
    """One deterministic initial-metric reduction stage."""

    metric: str
    reduction_mode: int
    reduction_target: int
    expected_schedule_epoch: int
    expected_reduction_epoch: int
    value_count: int
    output_count: int
    final_stage: bool


@dataclass(frozen=True, slots=True)
class FgmresV2FirstColumnReductionLaunch:
    """One canonical reduction stage in restart one, column zero."""

    metric: str
    reduction_mode: int
    reduction_target: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    expected_reduction_epoch: int
    value_count: int
    output_count: int
    logical_index: int
    final_stage: bool


@dataclass(frozen=True, slots=True)
class FgmresV2FirstColumnCompletionLaunch:
    """One immutable host submission in the column-zero completion slice.

    ``mode`` belongs to the code family selected by ``submission_kind``.
    Coordinates absent from a fixed kernel signature are ``None``.  The tuple
    returned by :func:`first_column_completion_launches_v2` never depends on
    the live DGKS flag; the device consumes ``device_gate_source``.
    """

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    logical_index: int | None
    row_index: int | None
    pass_index: int | None
    vector_gate: int | None
    reduction_target: int | None
    expected_reduction_epoch: int | None
    value_count: int | None
    output_count: int | None
    final_stage: bool | None
    device_gate_source: str | None


@dataclass(frozen=True, slots=True)
class FgmresV2FirstColumnCandidatePreparationLaunch:
    """One immutable submission in the fixed candidate-preparation prefix.

    The host-facing plan contains no candidate or triangular-breakdown input.
    Every row is always returned and the fixed device gates claim inactive
    epochs without host-side branching.
    """

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    logical_index: int | None
    row_index: int | None
    pass_index: int | None
    vector_gate: int | None
    reduction_target: int | None
    expected_reduction_epoch: int | None
    value_count: int | None
    output_count: int | None
    final_stage: bool | None
    device_gate_source: str | None


@dataclass(frozen=True, slots=True)
class FgmresV2FirstColumnCandidateResidualLaunch:
    """One immutable submission in the fixed candidate-residual prefix.

    The host always receives candidate SpMV, operator accept, in-place
    residual formation, and both residual metric trees.  Live candidate and
    triangular-breakdown state remains a device gate and is not a planner
    argument.
    """

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    logical_index: int | None
    row_index: int | None
    pass_index: int | None
    vector_gate: int | None
    reduction_target: int | None
    expected_reduction_epoch: int | None
    value_count: int | None
    output_count: int | None
    final_stage: bool | None
    device_gate_source: str | None


@dataclass(frozen=True, slots=True)
class FgmresV2FirstColumnCandidateScaleMetricsLaunch:
    """One immutable reduction submission in the candidate scale prefix.

    Trial and committed solution norms are always submitted.  Their exact
    device predicate is carried as immutable schedule metadata and never as
    a host branch input.
    """

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    logical_index: int | None
    row_index: int | None
    pass_index: int | None
    vector_gate: int | None
    reduction_target: int | None
    expected_reduction_epoch: int | None
    value_count: int | None
    output_count: int | None
    final_stage: bool | None
    device_gate_source: str | None


@dataclass(frozen=True, slots=True)
class FgmresV2FirstColumnPredecessorValidationLaunch:
    """One non-advancing device validation/seal submission."""

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    row_index: int
    pass_index: int
    expected_reduction_epoch: int
    admitted_mask_domain: tuple[int, ...]
    schedule_epoch_advances: bool
    reduction_epoch_advances: bool


@dataclass(frozen=True, slots=True)
class FgmresV2CanonicalPredecessorLaunch:
    """One row in the complete initial-to-sealed-column-zero schedule."""

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    logical_index: int | None = None
    row_index: int | None = None
    pass_index: int | None = None
    vector_gate: int | None = None
    reduction_target: int | None = None
    expected_reduction_epoch: int | None = None
    value_count: int | None = None
    output_count: int | None = None
    final_stage: bool | None = None
    device_gate_source: str | None = None
    reduction_tree_id: str | None = None


@dataclass(frozen=True, slots=True)
class FgmresV2FirstColumnCheckpointTransactionLaunch:
    """One immutable row in the fixed column-zero checkpoint transaction."""

    name: str
    submission_kind: str
    kernel_symbol: str
    mode: int
    expected_schedule_epoch: int
    expected_restart: int
    expected_column: int
    logical_index: int | None
    row_index: int | None
    pass_index: int | None
    vector_gate: int | None
    reduction_target: int | None
    expected_reduction_epoch: int | None
    value_count: int | None
    output_count: int | None
    final_stage: bool | None
    device_gate_source: str | None


@dataclass(frozen=True, slots=True)
class _HipRtcFgmresV2BindingWitness:
    runtime_api: _RuntimeModuleApi
    loaded_runtime: object
    loader_provenance_witness: object | None
    module_pointer: int
    function_pointers: tuple[tuple[str, int], ...]
    launch_callable: Any
    unload_callable: Any
    get_device_callable: Any
    module_device_ordinal: int
    expected_device_ordinal: int | None
    identity: HipRtcFgmresV2KernelIdentity
    identity_payload_hash: str
    identity_value_snapshot: tuple[Any, ...]
    launch_fence_ledger_state: _HipFgmresRtcLaunchFenceLedgerStateV1
    stream_synchronize_callable: Any | None = None
    stream_query_callable: Any | None = None
    memset_async_callable: Any | None = None


_KERNEL_BINDING_LOCK = threading.RLock()
_KERNEL_BINDINGS: weakref.WeakKeyDictionary[
    object,
    _HipRtcFgmresV2BindingWitness,
] = weakref.WeakKeyDictionary()


def _exact_function_pointer_values(value: object) -> tuple[tuple[str, int], ...]:
    """Return only an exact built-in tuple/str/int function-handle table."""

    if type(value) is not tuple:
        return ()
    rows: list[tuple[str, int]] = []
    for row in value:
        if (
            type(row) is not tuple
            or len(row) != 2
            or type(row[0]) is not str
            or not row[0]
            or type(row[1]) is not int
            or row[1] <= 0
        ):
            return ()
        rows.append((row[0], row[1]))
    return tuple(rows)


def _checkpoint_binding_snapshot_values(
    witness: _HipRtcFgmresV2BindingWitness,
) -> tuple[Any, ...]:
    return (
        id(witness.runtime_api),
        id(witness.loaded_runtime),
        id(witness.loader_provenance_witness),
        (type(witness.module_pointer), witness.module_pointer),
        tuple(
            (type(name), name, type(pointer), pointer)
            for name, pointer in witness.function_pointers
        ),
        id(witness.launch_callable),
        id(witness.unload_callable),
        id(witness.get_device_callable),
        (type(witness.module_device_ordinal), witness.module_device_ordinal),
        (type(witness.expected_device_ordinal), witness.expected_device_ordinal),
        id(witness.stream_synchronize_callable),
        id(witness.stream_query_callable),
        id(witness.memset_async_callable),
        id(witness.launch_fence_ledger_state),
        id(witness.identity),
        witness.identity_payload_hash,
    )


def _typed_identity_value(name: str, value: Any) -> tuple[Any, ...]:
    """Capture one exact-type identity value without replaying its hashes."""

    if type(value) is tuple:
        return (
            name,
            tuple,
            tuple((type(item), item) for item in value),
        )
    return (name, type(value), value)


def _kernel_identity_value_snapshot(
    identity: HipRtcFgmresV2KernelIdentity,
) -> tuple[Any, ...]:
    """Return an injective fixed-field snapshot of one validated identity.

    The compiler performs the authoritative semantic validation and canonical
    hashing before this witness is published.  Repeated launch and checkpoint
    operations only need to prove that none of those already-validated values
    drifted.  Keeping the exact Python type alongside every scalar also avoids
    equality aliases such as ``True == 1``.
    """

    hiprtc = identity.hiprtc_library
    runtime = identity.runtime_library
    return (
        ("identity", type(identity)),
        _typed_identity_value("schema_version", identity.schema_version),
        _typed_identity_value("abi_version", identity.abi_version),
        _typed_identity_value(
            "recurrence_abi_version",
            identity.recurrence_abi_version,
        ),
        _typed_identity_value("control_abi_version", identity.control_abi_version),
        _typed_identity_value("kernel_name", identity.kernel_name),
        _typed_identity_value("kernel_symbols", identity.kernel_symbols),
        _typed_identity_value("control_block_size", identity.control_block_size),
        _typed_identity_value("vector_block_size", identity.vector_block_size),
        _typed_identity_value(
            "reduction_values_per_block",
            identity.reduction_values_per_block,
        ),
        _typed_identity_value(
            "control_state_abi_hash",
            identity.control_state_abi_hash,
        ),
        _typed_identity_value("solve_record_abi_hash", identity.solve_record_abi_hash),
        _typed_identity_value(
            "kernel_interface_hash",
            identity.kernel_interface_hash,
        ),
        _typed_identity_value("source_resource", identity.source_resource),
        _typed_identity_value("source_sha256", identity.source_sha256),
        _typed_identity_value("compile_options", identity.compile_options),
        _typed_identity_value("architecture", identity.architecture),
        _typed_identity_value(
            "hiprtc_version_major",
            identity.hiprtc_version_major,
        ),
        _typed_identity_value(
            "hiprtc_version_minor",
            identity.hiprtc_version_minor,
        ),
        ("hiprtc_library", type(hiprtc)),
        _typed_identity_value(
            "hiprtc_library.discovery_source",
            hiprtc.discovery_source,
        ),
        _typed_identity_value(
            "hiprtc_library.requested_name",
            hiprtc.requested_name,
        ),
        _typed_identity_value("hiprtc_library.loaded_name", hiprtc.loaded_name),
        _typed_identity_value("hiprtc_library.resolved_path", hiprtc.resolved_path),
        _typed_identity_value("hiprtc_library.sha256", hiprtc.sha256),
        ("runtime_library", type(runtime)),
        _typed_identity_value(
            "runtime_library.discovery_source",
            runtime.discovery_source,
        ),
        _typed_identity_value(
            "runtime_library.requested_name",
            runtime.requested_name,
        ),
        _typed_identity_value("runtime_library.loaded_name", runtime.loaded_name),
        _typed_identity_value("runtime_library.resolved_path", runtime.resolved_path),
        _typed_identity_value("runtime_library.sha256", runtime.sha256),
        _typed_identity_value(
            "code_object_byte_length",
            identity.code_object_byte_length,
        ),
        _typed_identity_value("code_object_sha256", identity.code_object_sha256),
        _typed_identity_value("identity_hash", identity.identity_hash),
        _typed_identity_value(
            "_code_object_witness",
            identity._code_object_witness,
        ),
    )


def _require_expected_prior_pending_count(
    pending_streams: dict[int, int],
    *,
    stream_pointer: int,
    expected_count: int | None,
) -> None:
    """Require an exact pre-launch reservation map under the owner lock."""

    if expected_count is None:
        return
    if type(expected_count) is not int or not 0 <= expected_count <= _INT32_MAX:
        raise _launch_contract_error(
            "checkpoint expected prior pending count must be an exact "
            "nonnegative int32 value."
        )
    valid = (
        not pending_streams
        if expected_count == 0
        else (
            len(pending_streams) == 1
            and pending_streams.get(stream_pointer) == expected_count
        )
    )
    if not valid:
        raise _launch_contract_error(
            "checkpoint expected prior pending count does not match the exact "
            "leased stream reservation map."
        )


def _runtime_loader_provenance_witness(loaded_runtime: object) -> object | None:
    if type(loaded_runtime) is LoadedHipRuntime:
        return loaded_runtime._loader_provenance_witness()
    return None


def _query_current_device_ordinal(
    *,
    loaded_runtime: object,
    get_device_callable: Any,
    operation: str,
    launch_disposition: str | None = None,
) -> int:
    device = ctypes.c_int(-1)
    try:
        status = int(get_device_callable(ctypes.byref(device)))
    except Exception as exc:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_device_query_failed",
            f"{operation} hipGetDevice raised {type(exc).__name__}.",
            launch_disposition=launch_disposition,
        ) from exc
    if status != 0:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_device_query_failed",
            f"{operation} hipGetDevice failed: "
            f"{_runtime_error_string(loaded_runtime, status)}.",
            launch_disposition=launch_disposition,
        )
    ordinal = int(device.value)
    if ordinal < 0:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_device_query_invalid",
            f"{operation} hipGetDevice returned an invalid ordinal.",
            launch_disposition=launch_disposition,
        )
    return ordinal


def _require_expected_device_ordinal(
    witness: _HipRtcFgmresV2BindingWitness,
    *,
    operation: str,
    expected_device_ordinal: int | None = None,
    launch_disposition: str | None = None,
) -> int:
    expected = (
        witness.expected_device_ordinal
        if expected_device_ordinal is None
        else expected_device_ordinal
    )
    if expected is None:
        expected = witness.module_device_ordinal
    if (
        isinstance(expected, bool)
        or not isinstance(expected, int)
        or expected < 0
        or expected > _INT32_MAX
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_device_ordinal_invalid",
            f"{operation} expected device ordinal is invalid.",
            launch_disposition=launch_disposition,
        )
    current = _query_current_device_ordinal(
        loaded_runtime=witness.loaded_runtime,
        get_device_callable=witness.get_device_callable,
        operation=operation,
        launch_disposition=launch_disposition,
    )
    if expected != witness.module_device_ordinal or current != expected:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_device_mismatch",
            f"{operation} requires module device {witness.module_device_ordinal}, "
            f"expected device {expected}, and current device {current} to match.",
            launch_disposition=launch_disposition,
        )
    return current


class HipRtcFgmresV2Kernel:
    """Loaded recurrence-v2 module with explicit completion-fence ownership."""

    __slots__ = (
        "__weakref__",
        "_runtime",
        "_module_pointer",
        "_function_pointers",
        "_identity",
        "_identity_payload_hash_snapshot",
        "_identity_value_snapshot",
        "_ownership_cell",
        "_closed",
        "_pending_streams",
        "_checkpoint_owner_lock",
        "_checkpoint_owner_token",
        "_checkpoint_owner_poisoned",
        "_checkpoint_owner_binding_snapshot",
        "_launch_fence_ledger_state",
    )

    def __init__(
        self,
        *,
        runtime: _RuntimeModuleApi,
        module: ctypes.c_void_p,
        functions: dict[str, ctypes.c_void_p],
        identity: HipRtcFgmresV2KernelIdentity,
        ownership_cell: _HipRtcFgmresV2ModuleOwnershipCell | None = None,
        _owner_mint: object | None = None,
    ) -> None:
        if _owner_mint is not _KERNEL_OWNER_MINT:
            raise TypeError(
                "HipRtcFgmresV2Kernel is issued only by the fixed-source compiler."
            )
        module_pointer = _runtime_pointer(module, "module")
        if (
            type(ownership_cell) is not _HipRtcFgmresV2ModuleOwnershipCell
            or ownership_cell.module is not module
            or type(ownership_cell.owner) is not _HipRtcFgmresV2ModuleCleanupOwner
            or ownership_cell.owner._ownership_cell is not ownership_cell
        ):
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_module_ownership_invalid",
                "Kernel construction requires the exact preallocated module owner.",
            )
        if tuple(functions) != tuple(key for key, _ in _SYMBOL_ITEMS):
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_binding_invalid",
                "The fixed kernel function binding set is incomplete or reordered.",
            )
        function_pointers = tuple(
            (name, _runtime_pointer(functions[name], f"function[{name}]"))
            for name, _ in _SYMBOL_ITEMS
        )
        _validate_identity(identity)
        try:
            get_device = runtime._runtime.bind(
                "hipGetDevice",
                [ctypes.POINTER(ctypes.c_int)],
                ctypes.c_int,
            )
        except Exception as exc:
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_device_query_unavailable",
                "The exact module runtime could not bind hipGetDevice: "
                f"{type(exc).__name__}.",
            ) from exc
        module_device_ordinal = _query_current_device_ordinal(
            loaded_runtime=runtime._runtime,
            get_device_callable=get_device,
            operation="fixed module binding",
        )
        self._runtime = runtime
        self._module_pointer = module_pointer
        self._function_pointers = function_pointers
        self._identity = identity
        self._identity_payload_hash_snapshot = canonical_hash(identity.to_dict())
        self._identity_value_snapshot = _kernel_identity_value_snapshot(identity)
        self._ownership_cell = ownership_cell
        self._closed = False
        self._pending_streams: dict[int, int] = {}
        self._checkpoint_owner_lock = threading.RLock()
        self._checkpoint_owner_token: object | None = None
        self._checkpoint_owner_poisoned = False
        self._checkpoint_owner_binding_snapshot: tuple[Any, ...] | None = None
        self._launch_fence_ledger_state = _HipFgmresRtcLaunchFenceLedgerStateV1()
        witness = _HipRtcFgmresV2BindingWitness(
            runtime_api=runtime,
            loaded_runtime=runtime._runtime,
            loader_provenance_witness=_runtime_loader_provenance_witness(
                runtime._runtime
            ),
            module_pointer=module_pointer,
            function_pointers=function_pointers,
            launch_callable=runtime._launch_kernel,
            unload_callable=runtime._unload,
            get_device_callable=get_device,
            module_device_ordinal=module_device_ordinal,
            expected_device_ordinal=None,
            identity=identity,
            identity_payload_hash=self._identity_payload_hash_snapshot,
            identity_value_snapshot=self._identity_value_snapshot,
            launch_fence_ledger_state=self._launch_fence_ledger_state,
        )
        with _KERNEL_BINDING_LOCK:
            _KERNEL_BINDINGS[self] = witness

    @property
    def identity(self) -> HipRtcFgmresV2KernelIdentity:
        return self._identity

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def _unload_disposition(self) -> str:
        return self._ownership_cell.unload_disposition

    @_unload_disposition.setter
    def _unload_disposition(self, value: str) -> None:
        self._ownership_cell.unload_disposition = value

    @property
    def pending_stream_count(self) -> int:
        with self._checkpoint_owner_lock:
            return len(self._pending_streams)

    def _validated_binding(self) -> _HipRtcFgmresV2BindingWitness:
        with _KERNEL_BINDING_LOCK:
            witness = _KERNEL_BINDINGS.get(self)
            try:
                identity_value_snapshot = _kernel_identity_value_snapshot(
                    self._identity
                )
                loader_provenance_witness = _runtime_loader_provenance_witness(
                    self._runtime._runtime
                )
            except Exception as exc:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_binding_changed",
                    "The fixed kernel identity changed after module load.",
                ) from exc
            if (
                witness is None
                or self._runtime is not witness.runtime_api
                or self._runtime._runtime is not witness.loaded_runtime
                or loader_provenance_witness is not witness.loader_provenance_witness
                or self._runtime._launch_kernel is not witness.launch_callable
                or self._runtime._unload is not witness.unload_callable
                or self._ownership_cell.owner is not self
                or type(self._module_pointer) is not int
                or self._module_pointer <= 0
                or type(witness.module_pointer) is not int
                or witness.module_pointer <= 0
                or self._module_pointer != witness.module_pointer
                or not self._function_pointers
                or _exact_function_pointer_values(self._function_pointers)
                != self._function_pointers
                or _exact_function_pointer_values(witness.function_pointers)
                != self._function_pointers
                or self._function_pointers != witness.function_pointers
                or not callable(witness.get_device_callable)
                or (
                    witness.stream_query_callable is not None
                    and not callable(witness.stream_query_callable)
                )
                or (
                    witness.memset_async_callable is not None
                    and not callable(witness.memset_async_callable)
                )
                or type(witness.launch_fence_ledger_state)
                is not _HipFgmresRtcLaunchFenceLedgerStateV1
                or self._launch_fence_ledger_state
                is not witness.launch_fence_ledger_state
                or type(witness.module_device_ordinal) is not int
                or witness.module_device_ordinal < 0
                or (
                    witness.expected_device_ordinal is not None
                    and (
                        type(witness.expected_device_ordinal) is not int
                        or witness.expected_device_ordinal < 0
                    )
                )
                or self._identity is not witness.identity
                or self._identity_payload_hash_snapshot != witness.identity_payload_hash
                or self._identity_value_snapshot != witness.identity_value_snapshot
                or identity_value_snapshot != witness.identity_value_snapshot
            ):
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_binding_changed",
                    "The loaded module, function handles, runtime callables, or "
                    "identity changed after fixed-source compilation.",
                )
            return witness

    def __enter__(self) -> HipRtcFgmresV2Kernel:
        self._require_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def launch_control(
        self,
        stream: Any,
        control_mode: int,
        expected_schedule_epoch: int,
        expected_restart: int,
        expected_column: int,
        row_index: int,
        pass_index: int,
        free_dof_count: int,
        restart_dimension: int,
        max_iterations: int,
        maximum_restart_count: int,
        stagnation_checkpoint_limit: int,
        absolute_tolerance: float,
        relative_tolerance: float,
        authoritative_tolerance: float,
        stagnation_relative_tolerance: float,
        divergence_factor: float,
        dense_base: Any,
        control_state_base: Any,
        solve_record_base: Any,
        *,
        _checkpoint_owner_token: object | None = None,
        _checkpoint_expected_prior_pending_count: int | None = None,
        _checkpoint_audit_descriptor_hash: str | None = None,
    ) -> None:
        self._require_open()
        mode = _exact_enum(
            control_mode,
            "control_mode",
            _IMPLEMENTED_CONTROL_MODES,
        )
        checked_schedule_epoch = _schedule_epoch(expected_schedule_epoch)
        checked_expected_restart = _bounded_int(
            expected_restart,
            "expected_restart",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_ITERATIONS,
        )
        checked_expected_column = _bounded_int(
            expected_column,
            "expected_column",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION - 1,
        )
        checked_row = _bounded_int(
            row_index,
            "row_index",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION - 1,
        )
        checked_pass = _bounded_int(pass_index, "pass_index", minimum=-1, maximum=1)
        n = _positive_int32(free_dof_count, "free_dof_count")
        restart = _bounded_int(
            restart_dimension,
            "restart_dimension",
            minimum=1,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
        )
        iterations = _bounded_int(
            max_iterations,
            "max_iterations",
            minimum=0,
            maximum=HIP_FGMRES_MAX_ITERATIONS,
        )
        expected_restarts = (
            0 if iterations == 0 else (iterations + restart - 1) // restart
        )
        restarts = _bounded_int(
            maximum_restart_count,
            "maximum_restart_count",
            minimum=0,
            maximum=HIP_FGMRES_MAX_ITERATIONS,
        )
        if restarts != expected_restarts:
            raise _launch_contract_error(
                "maximum_restart_count must equal ceil(max_iterations/"
                "restart_dimension)."
            )
        _validate_control_launch(
            mode,
            checked_schedule_epoch,
            checked_expected_restart,
            checked_expected_column,
            checked_row,
            checked_pass,
            n,
            restart,
            iterations,
        )
        stagnation_limit = _bounded_int(
            stagnation_checkpoint_limit,
            "stagnation_checkpoint_limit",
            minimum=2,
            maximum=16,
        )
        atol = _nonnegative_float64(absolute_tolerance, "absolute_tolerance")
        rtol = _nonnegative_float64(relative_tolerance, "relative_tolerance")
        if atol == 0.0 and rtol == 0.0:
            raise _launch_contract_error(
                "absolute_tolerance and relative_tolerance must not both be zero."
            )
        authoritative = _nonnegative_float64(
            authoritative_tolerance,
            "authoritative_tolerance",
        )
        stagnation = _positive_float64(
            stagnation_relative_tolerance,
            "stagnation_relative_tolerance",
        )
        if stagnation >= 1.0:
            raise _launch_contract_error(
                "stagnation_relative_tolerance must be less than one."
            )
        divergence = _positive_float64(divergence_factor, "divergence_factor")
        if divergence <= 1.0:
            raise _launch_contract_error("divergence_factor must exceed one.")
        pointers = _pointer_arguments(
            (
                ("dense_base", dense_base),
                ("control_state_base", control_state_base),
                ("solve_record_base", solve_record_base),
            )
        )
        self._launch(
            "control",
            stream=stream,
            grid_x=1,
            block_x=HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE,
            arguments=(
                ctypes.c_int(mode),
                ctypes.c_int(checked_schedule_epoch),
                ctypes.c_int(checked_expected_restart),
                ctypes.c_int(checked_expected_column),
                ctypes.c_int(checked_row),
                ctypes.c_int(checked_pass),
                ctypes.c_int(n),
                ctypes.c_int(restart),
                ctypes.c_int(iterations),
                ctypes.c_int(restarts),
                ctypes.c_int(stagnation_limit),
                ctypes.c_double(atol),
                ctypes.c_double(rtol),
                ctypes.c_double(authoritative),
                ctypes.c_double(stagnation),
                ctypes.c_double(divergence),
                *(ctypes.c_void_p(value) for value in pointers),
            ),
            operation="FGMRES v2 control",
            checkpoint_owner_token=_checkpoint_owner_token,
            checkpoint_expected_prior_pending_count=(
                _checkpoint_expected_prior_pending_count
            ),
            checkpoint_audit_descriptor_hash=_checkpoint_audit_descriptor_hash,
        )

    def launch_vector(
        self,
        stream: Any,
        vector_mode: int,
        vector_gate: int,
        expected_schedule_epoch: int,
        expected_restart: int,
        expected_column: int,
        free_dof_count: int,
        logical_index: int,
        reduced_state_base: Any,
        reduced_load_base: Any,
        inverse_diagonal_base: Any,
        solution_x_base: Any,
        true_residual_base: Any,
        work_w_base: Any,
        basis_v_base: Any,
        basis_z_base: Any,
        dense_base: Any,
        control_state_base: Any,
        solve_record_base: Any,
        *,
        _checkpoint_owner_token: object | None = None,
        _checkpoint_expected_prior_pending_count: int | None = None,
        _checkpoint_audit_descriptor_hash: str | None = None,
    ) -> None:
        self._require_open()
        mode = _exact_enum(vector_mode, "vector_mode", _IMPLEMENTED_VECTOR_MODES)
        gate = _exact_enum(
            vector_gate,
            "vector_gate",
            frozenset(
                {
                    _VECTOR_GATES["ACTIVE"],
                    _VECTOR_GATES["DGKS_SECOND_PASS"],
                    _VECTOR_GATES["CANDIDATE_REQUIRED"],
                    _VECTOR_GATES["COMMIT_REQUIRED"],
                }
            ),
        )
        checked_schedule_epoch = _schedule_epoch(expected_schedule_epoch)
        checked_expected_restart = _bounded_int(
            expected_restart,
            "expected_restart",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_ITERATIONS,
        )
        checked_expected_column = _bounded_int(
            expected_column,
            "expected_column",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION - 1,
        )
        n = _positive_int32(free_dof_count, "free_dof_count")
        index = _bounded_int(
            logical_index,
            "logical_index",
            minimum=0,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
        )
        _validate_vector_launch(
            mode,
            gate,
            checked_schedule_epoch,
            checked_expected_restart,
            checked_expected_column,
            index,
            n,
        )
        pointers = _pointer_arguments(
            (
                ("reduced_state_base", reduced_state_base),
                ("reduced_load_base", reduced_load_base),
                ("inverse_diagonal_base", inverse_diagonal_base),
                ("solution_x_base", solution_x_base),
                ("true_residual_base", true_residual_base),
                ("work_w_base", work_w_base),
                ("basis_v_base", basis_v_base),
                ("basis_z_base", basis_z_base),
                ("dense_base", dense_base),
                ("control_state_base", control_state_base),
                ("solve_record_base", solve_record_base),
            )
        )
        _validate_vector_pointer_aliases(mode, pointers)
        self._launch(
            "vector",
            stream=stream,
            grid_x=_vector_block_count(n),
            block_x=HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE,
            arguments=(
                ctypes.c_int(mode),
                ctypes.c_int(gate),
                ctypes.c_int(checked_schedule_epoch),
                ctypes.c_int(checked_expected_restart),
                ctypes.c_int(checked_expected_column),
                ctypes.c_int(n),
                ctypes.c_int(index),
                *(ctypes.c_void_p(value) for value in pointers),
            ),
            operation="FGMRES v2 vector",
            checkpoint_owner_token=_checkpoint_owner_token,
            checkpoint_expected_prior_pending_count=(
                _checkpoint_expected_prior_pending_count
            ),
            checkpoint_audit_descriptor_hash=_checkpoint_audit_descriptor_hash,
        )

    def launch_csr_spmv_indexed(
        self,
        stream: Any,
        spmv_mode: int,
        expected_schedule_epoch: int,
        expected_restart: int,
        expected_column: int,
        free_dof_count: int,
        nonzero_count: int,
        logical_index: int,
        row_ptr_base: Any,
        column_indices_base: Any,
        values_base: Any,
        solution_x_base: Any,
        work_w_base: Any,
        basis_v_base: Any,
        basis_z_base: Any,
        control_state_base: Any,
        solve_record_base: Any,
        *,
        _checkpoint_owner_token: object | None = None,
        _checkpoint_expected_prior_pending_count: int | None = None,
        _checkpoint_audit_descriptor_hash: str | None = None,
    ) -> None:
        self._require_open()
        mode = _exact_enum(
            spmv_mode,
            "spmv_mode",
            _IMPLEMENTED_SPMV_MODES,
        )
        checked_schedule_epoch = _schedule_epoch(expected_schedule_epoch)
        checked_expected_restart = _bounded_int(
            expected_restart,
            "expected_restart",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_ITERATIONS,
        )
        checked_expected_column = _bounded_int(
            expected_column,
            "expected_column",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION - 1,
        )
        n = _positive_int32(free_dof_count, "free_dof_count")
        nnz = _positive_int32(nonzero_count, "nonzero_count")
        if nnz < n:
            raise _launch_contract_error(
                "nonzero_count must be at least free_dof_count."
            )
        index = _bounded_int(
            logical_index,
            "logical_index",
            minimum=0,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
        )
        _validate_spmv_launch(
            mode,
            checked_schedule_epoch,
            checked_expected_restart,
            checked_expected_column,
            index,
            n,
        )
        pointers = _pointer_arguments(
            (
                ("row_ptr_base", row_ptr_base),
                ("column_indices_base", column_indices_base),
                ("values_base", values_base),
                ("solution_x_base", solution_x_base),
                ("work_w_base", work_w_base),
                ("basis_v_base", basis_v_base),
                ("basis_z_base", basis_z_base),
                ("control_state_base", control_state_base),
                ("solve_record_base", solve_record_base),
            )
        )
        _validate_spmv_pointer_aliases(mode, pointers)
        self._launch(
            "csr_spmv_indexed",
            stream=stream,
            grid_x=_vector_block_count(n),
            block_x=HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE,
            arguments=(
                ctypes.c_int(mode),
                ctypes.c_int(checked_schedule_epoch),
                ctypes.c_int(checked_expected_restart),
                ctypes.c_int(checked_expected_column),
                ctypes.c_int(n),
                ctypes.c_int(nnz),
                ctypes.c_int(index),
                *(ctypes.c_void_p(value) for value in pointers),
            ),
            operation="FGMRES v2 indexed CSR SpMV",
            checkpoint_owner_token=_checkpoint_owner_token,
            checkpoint_expected_prior_pending_count=(
                _checkpoint_expected_prior_pending_count
            ),
            checkpoint_audit_descriptor_hash=_checkpoint_audit_descriptor_hash,
        )

    def launch_reduction(
        self,
        stream: Any,
        reduction_mode: int,
        reduction_target: int,
        expected_schedule_epoch: int,
        expected_restart: int,
        expected_column: int,
        expected_reduction_epoch: int,
        value_count: int,
        logical_index: int,
        reduced_load_base: Any,
        solution_x_base: Any,
        true_residual_base: Any,
        work_w_base: Any,
        basis_v_base: Any,
        reduction_input_base: Any,
        reduction_output_base: Any,
        control_state_base: Any,
        solve_record_base: Any,
        *,
        _checkpoint_owner_token: object | None = None,
        _checkpoint_expected_prior_pending_count: int | None = None,
        _checkpoint_audit_descriptor_hash: str | None = None,
    ) -> None:
        self._require_open()
        mode = _exact_enum(
            reduction_mode,
            "reduction_mode",
            _IMPLEMENTED_REDUCTION_MODES,
        )
        target = _exact_enum(
            reduction_target,
            "reduction_target",
            _IMPLEMENTED_REDUCTION_TARGETS,
        )
        checked_schedule_epoch = _schedule_epoch(expected_schedule_epoch)
        checked_expected_restart = _bounded_int(
            expected_restart,
            "expected_restart",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_ITERATIONS,
        )
        checked_expected_column = _bounded_int(
            expected_column,
            "expected_column",
            minimum=-1,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION - 1,
        )
        checked_epoch = _bounded_int(
            expected_reduction_epoch,
            "expected_reduction_epoch",
            minimum=0,
            maximum=_INT32_MAX - 1,
        )
        count = _positive_int32(value_count, "value_count")
        _validate_reduction_mode_target(mode, target, count)
        index = _bounded_int(
            logical_index,
            "logical_index",
            minimum=0,
            maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
        )
        _validate_reduction_coordinates(
            mode,
            target,
            checked_schedule_epoch,
            checked_expected_restart,
            checked_expected_column,
            checked_epoch,
            count,
            index,
        )
        pointers = _pointer_arguments(
            (
                ("reduced_load_base", reduced_load_base),
                ("solution_x_base", solution_x_base),
                ("true_residual_base", true_residual_base),
                ("work_w_base", work_w_base),
                ("basis_v_base", basis_v_base),
                ("reduction_input_base", reduction_input_base),
                ("reduction_output_base", reduction_output_base),
                ("control_state_base", control_state_base),
                ("solve_record_base", solve_record_base),
            )
        )
        _validate_reduction_pointer_aliases(mode, pointers)
        self._launch(
            "reduce",
            stream=stream,
            grid_x=reduction_output_count_v2(count),
            block_x=HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE,
            arguments=(
                ctypes.c_int(mode),
                ctypes.c_int(target),
                ctypes.c_int(checked_schedule_epoch),
                ctypes.c_int(checked_expected_restart),
                ctypes.c_int(checked_expected_column),
                ctypes.c_int(checked_epoch),
                ctypes.c_int(count),
                ctypes.c_int(index),
                *(ctypes.c_void_p(value) for value in pointers),
            ),
            operation="FGMRES v2 deterministic reduction",
            checkpoint_owner_token=_checkpoint_owner_token,
            checkpoint_expected_prior_pending_count=(
                _checkpoint_expected_prior_pending_count
            ),
            checkpoint_audit_descriptor_hash=_checkpoint_audit_descriptor_hash,
        )

    def acknowledge_stream_completion(
        self,
        stream: Any,
        *,
        _checkpoint_owner_token: object | None = None,
    ) -> None:
        with self._checkpoint_owner_lock, self._ownership_cell.lock:
            self._require_open()
            self._require_checkpoint_owner_access(
                _checkpoint_owner_token,
                allow_poisoned=True,
            )
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="stream completion acknowledgement",
            )
            stream_value = _runtime_pointer(stream, "stream")
            if stream_value not in self._pending_streams:
                raise _launch_contract_error(
                    "stream has no pending FGMRES v2 launch to acknowledge."
                )
            del self._pending_streams[stream_value]

    def close(
        self,
        *,
        _checkpoint_owner_token: object | None = None,
    ) -> None:
        with self._checkpoint_owner_lock, self._ownership_cell.lock:
            if self._closed:
                return
            if (
                self._ownership_cell.owner is None
                and self._unload_disposition == "external_unload_succeeded"
            ):
                self._finish_unload_success()
                return
            if self._ownership_cell.owner is not self:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_module_ownership_changed",
                    "The kernel no longer owns its native module authority.",
                )
            if self._unload_disposition == "external_unload_succeeded":
                self._finish_unload_success()
                return
            if self._unload_disposition == "unload_preflight":
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_close_reentrant",
                    "HIPRTC FGMRES v2 kernel close is already in progress.",
                )
            if self._unload_disposition in {
                "unload_call_inflight",
                "unload_outcome_uncertain",
            }:
                self._unload_disposition = "unload_outcome_uncertain"
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_module_unload_outcome_uncertain",
                    "A prior hipModuleUnload outcome is uncertain; the module handle will not be retried.",
                )
            status: int | None = None
            witness: _HipRtcFgmresV2BindingWitness | None = None
            try:
                self._unload_disposition = "unload_preflight"
                self._require_checkpoint_owner_access(
                    _checkpoint_owner_token,
                    allow_poisoned=True,
                )
                if self._pending_streams:
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_completion_fence_required",
                        "HIPRTC FGMRES v2 module has pending stream work; "
                        "acknowledge an observed completion fence before unload.",
                    )
                witness = self._validated_binding()
                _require_expected_device_ordinal(
                    witness,
                    operation="module close",
                )
                self._unload_disposition = "unload_call_inflight"
                status = int(
                    witness.unload_callable(ctypes.c_void_p(witness.module_pointer))
                )
                if status != 0:
                    self._unload_disposition = "live"
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_module_unload_failed",
                        "hipModuleUnload failed: "
                        f"{_runtime_error_string(witness.loaded_runtime, status)}.",
                    )
                self._unload_disposition = "external_unload_succeeded"
            except HipRtcFgmresV2Error:
                if self._unload_disposition == "unload_preflight":
                    self._unload_disposition = "live"
                elif self._unload_disposition == "unload_call_inflight":
                    self._unload_disposition = "unload_outcome_uncertain"
                raise
            except Exception as exc:
                self._unload_disposition = self._unload_failure_disposition(status)
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_module_unload_failed",
                    f"hipModuleUnload raised {type(exc).__name__}.",
                ) from exc
            except BaseException:
                self._unload_disposition = self._unload_failure_disposition(status)
                raise
            self._finish_unload_success(expected_witness=witness)

    def _unload_failure_disposition(self, status: int | None) -> str:
        if self._unload_disposition == "unload_preflight":
            return "live"
        if status == 0:
            return "external_unload_succeeded"
        if status is not None:
            return "live"
        return "unload_outcome_uncertain"

    def _finish_unload_success(
        self,
        *,
        expected_witness: _HipRtcFgmresV2BindingWitness | None = None,
    ) -> None:
        """Retire handles idempotently after one known-successful unload."""

        with self._ownership_cell.lock:
            binding_changed = False
            cell_owner = self._ownership_cell.owner
            if cell_owner is self:
                self._ownership_cell.owner = None
                self._ownership_cell.preowner = None
            elif cell_owner is not None:
                binding_changed = True
            with _KERNEL_BINDING_LOCK:
                current_witness = _KERNEL_BINDINGS.get(self)
                if (
                    expected_witness is not None
                    and current_witness is not expected_witness
                ):
                    binding_changed = True
                _KERNEL_BINDINGS.pop(self, None)
            self._module_pointer = 0
            self._function_pointers = ()
            self._pending_streams.clear()
            self._checkpoint_owner_token = None
            self._checkpoint_owner_poisoned = False
            self._checkpoint_owner_binding_snapshot = None
            self._closed = True
            self._unload_disposition = "terminal"
            if binding_changed:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_binding_changed",
                    "The fixed binding registry changed during module unload.",
                )

    def _acquire_checkpoint_transaction_owner(
        self,
        expected_device_ordinal: int | None = None,
        *,
        _checkpoint_owner_token: object,
    ) -> object:
        """Acquire the sole process-local capability for a checkpoint slice."""

        token, _ = self._acquire_checkpoint_owner_and_binding_snapshot(
            expected_device_ordinal,
            checkpoint_owner_token=_checkpoint_owner_token,
        )
        return token

    def _acquire_checkpoint_transaction_owner_and_binding_snapshot(
        self,
        expected_device_ordinal: int | None = None,
        *,
        _checkpoint_owner_token: object,
    ) -> tuple[object, tuple[Any, ...]]:
        """Atomically acquire a lease and its immutable compiler binding."""

        return self._acquire_checkpoint_owner_and_binding_snapshot(
            expected_device_ordinal,
            checkpoint_owner_token=_checkpoint_owner_token,
        )

    def _acquire_checkpoint_owner_and_binding_snapshot(
        self,
        expected_device_ordinal: int | None,
        *,
        checkpoint_owner_token: object,
    ) -> tuple[object, tuple[Any, ...]]:
        if type(checkpoint_owner_token) is not object:
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_checkpoint_lease_token_invalid",
                "Checkpoint lease acquisition requires one exact preissued token.",
            )
        with self._checkpoint_owner_lock:
            self._require_open()
            if self._pending_streams:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_lease_fence_required",
                    "A checkpoint lease may be acquired only after every earlier "
                    "raw launch has an observed and acknowledged fence.",
                )
            if self._checkpoint_owner_token is not None:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_lease_active",
                    "The HIPRTC FGMRES v2 kernel already has a checkpoint lease.",
                )
            if self._checkpoint_owner_poisoned:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_lease_poisoned",
                    "The HIPRTC FGMRES v2 checkpoint lease is poisoned.",
                )
            witness = self._validated_binding()
            current_device_ordinal = _require_expected_device_ordinal(
                witness,
                operation="checkpoint lease acquisition",
                expected_device_ordinal=expected_device_ordinal,
            )
            stream_synchronize = witness.stream_synchronize_callable
            if witness.stream_synchronize_callable is None:
                try:
                    stream_synchronize = witness.loaded_runtime.bind(
                        "hipStreamSynchronize",
                        [ctypes.c_void_p],
                        ctypes.c_int,
                    )
                except Exception as exc:
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_checkpoint_sync_unavailable",
                        "The exact module runtime could not bind "
                        f"hipStreamSynchronize: {type(exc).__name__}.",
                    ) from exc
            stream_query = witness.stream_query_callable
            if witness.stream_query_callable is None:
                try:
                    stream_query = witness.loaded_runtime.bind(
                        "hipStreamQuery",
                        [ctypes.c_void_p],
                        ctypes.c_int,
                    )
                except Exception as exc:
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_checkpoint_query_unavailable",
                        "The exact module runtime could not bind "
                        f"hipStreamQuery: {type(exc).__name__}.",
                    ) from exc
            memset_async = witness.memset_async_callable
            if witness.memset_async_callable is None:
                try:
                    memset_async = witness.loaded_runtime.bind(
                        "hipMemsetAsync",
                        [
                            ctypes.c_void_p,
                            ctypes.c_int,
                            ctypes.c_size_t,
                            ctypes.c_void_p,
                        ],
                        ctypes.c_int,
                    )
                except Exception as exc:
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_checkpoint_memset_unavailable",
                        "The exact module runtime could not bind "
                        f"hipMemsetAsync: {type(exc).__name__}.",
                    ) from exc
            prior_witness = witness
            witness = replace(
                witness,
                stream_synchronize_callable=stream_synchronize,
                stream_query_callable=stream_query,
                memset_async_callable=memset_async,
                expected_device_ordinal=current_device_ordinal,
            )
            self._checkpoint_owner_token = checkpoint_owner_token
            with _KERNEL_BINDING_LOCK:
                if _KERNEL_BINDINGS.get(self) is not prior_witness:
                    # This is a definitive pre-publication CAS rejection, not
                    # an ambiguous interruption.  No owner binding was
                    # installed, so retaining the provisional token would
                    # strand the kernel in a half-acquired state whose normal
                    # release path cannot validate the forged registry row.
                    self._checkpoint_owner_token = None
                    self._checkpoint_owner_binding_snapshot = None
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_binding_changed",
                        "The fixed binding registry changed during lease setup.",
                    )
                _KERNEL_BINDINGS[self] = witness
            snapshot = _checkpoint_binding_snapshot_values(witness)
            self._checkpoint_owner_binding_snapshot = snapshot
            return checkpoint_owner_token, snapshot

    def _poison_checkpoint_transaction_owner(self, token: object) -> None:
        """Permanently forbid another launch while retaining fence ownership."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_identity(token)
            self._validated_binding()
            self._checkpoint_owner_poisoned = True

    def _release_checkpoint_transaction_owner_without_work(
        self,
        token: object,
    ) -> None:
        """Release a constructor-time lease that never submitted device work."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_identity(token)
            if self._pending_streams:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_lease_fence_required",
                    "A checkpoint lease with pending work cannot be released.",
                )
            witness = self._validated_binding()
            released_witness = replace(witness, expected_device_ordinal=None)
            with _KERNEL_BINDING_LOCK:
                if _KERNEL_BINDINGS.get(self) is not witness:
                    raise HipRtcFgmresV2Error(
                        "hip_rtc_fgmres_v2_binding_changed",
                        "The fixed binding registry changed during lease release.",
                    )
                _KERNEL_BINDINGS[self] = released_witness
            self._checkpoint_owner_token = None
            self._checkpoint_owner_poisoned = False
            self._checkpoint_owner_binding_snapshot = None

    def _checkpoint_runtime_owner(self, token: object) -> object:
        """Return the exact loaded runtime bound to the leased code object."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_identity(token)
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint runtime authority",
            )
            return witness.loaded_runtime

    def _checkpoint_binding_snapshot(self, token: object) -> tuple[Any, ...]:
        """Return the immutable compiler-issued binding witness for a lease."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_identity(token)
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint binding authority",
            )
            return _checkpoint_binding_snapshot_values(witness)

    def _checkpoint_pending_stream_count(self, token: object) -> int:
        """Return exact pending-stream ownership under the checkpoint lease."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_identity(token)
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint pending observation",
            )
            return len(self._pending_streams)

    def _checkpoint_pending_snapshot(
        self,
        token: object,
    ) -> tuple[tuple[int, int], ...]:
        """Return the exact stream/reservation map under the owner lock."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_identity(token)
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint pending snapshot",
            )
            return tuple(sorted(self._pending_streams.items()))

    def _checkpoint_launch_fence_ledger_snapshot_v1(
        self,
        token: object,
        mint: object,
    ) -> tuple[
        _HipFgmresRtcLaunchFenceLedgerStateV1,
        Any,
        tuple[Any, ...],
    ]:
        """Return the exact lease-bound RTC ordinal snapshot to its auditor."""

        if mint is not _RTC_LAUNCH_FENCE_LEDGER_SNAPSHOT_MINT_V1:
            raise PermissionError("invalid RTC launch/fence ledger snapshot mint")
        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_identity(token)
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint launch/fence ledger observation",
            )
            state = witness.launch_fence_ledger_state
            return (
                state,
                state.snapshot(),
                _checkpoint_binding_snapshot_values(witness),
            )

    def _consume_checkpoint_pending_after_fence(
        self,
        token: object,
        stream: Any,
    ) -> int:
        """Atomically consume one fenced stream's launch reservations."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_access(token, allow_poisoned=True)
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint fence acknowledgement",
            )
            stream_value = _runtime_pointer(stream, "stream")
            return self._pending_streams.pop(stream_value, 0)

    def _synchronize_checkpoint_stream(self, token: object, stream: Any) -> None:
        """Observe a fence through the exact runtime owning this code object."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_access(token, allow_poisoned=True)
            stream_value = _runtime_pointer(stream, "stream")
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint stream synchronization",
            )
            stream_synchronize = witness.stream_synchronize_callable
            if stream_synchronize is None:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_sync_unavailable",
                    "The exact runtime fence callable is absent from the lease.",
                )
            ticket = witness.launch_fence_ledger_state.begin(
                "fence",
                _fence_descriptor_hash_v1(),
            )
            try:
                raw_status = stream_synchronize(ctypes.c_void_p(stream_value))
            except BaseException as exc:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="ambiguous",
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_sync_failed",
                    f"hipStreamSynchronize raised {type(exc).__name__}.",
                ) from exc
            if type(raw_status) is not int:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="ambiguous",
                )
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_sync_failed",
                    "hipStreamSynchronize returned a non-exact status value.",
                )
            try:
                status = int(raw_status)
            except BaseException as exc:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="ambiguous",
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_sync_failed",
                    f"hipStreamSynchronize status handling raised "
                    f"{type(exc).__name__}.",
                ) from exc
            if status != 0:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="rejected",
                )
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_sync_failed",
                    "hipStreamSynchronize failed: "
                    f"{self._runtime.error_string(status)}.",
                )
            witness.launch_fence_ledger_state.finish(
                ticket,
                disposition="success",
            )

    def _query_checkpoint_stream_completion(
        self,
        token: object,
        stream: Any,
    ) -> bool:
        """Query one exact leased pending stream without consuming ownership."""

        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_access(token, allow_poisoned=True)
            stream_value = _runtime_pointer(stream, "stream")
            if (
                len(self._pending_streams) != 1
                or type(self._pending_streams.get(stream_value)) is not int
                or self._pending_streams[stream_value] <= 0
            ):
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_query_stream_invalid",
                    "Checkpoint completion may query only the exact leased "
                    "stream with positive pending reservations.",
                )
            witness = self._validated_binding()
            current_snapshot = _checkpoint_binding_snapshot_values(witness)
            if (
                self._checkpoint_owner_binding_snapshot is None
                or current_snapshot != self._checkpoint_owner_binding_snapshot
            ):
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_binding_changed",
                    "The checkpoint query binding changed after lease acquisition.",
                )
            _require_expected_device_ordinal(
                witness,
                operation="checkpoint stream completion query",
            )
            stream_query = witness.stream_query_callable
            if stream_query is None:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_query_unavailable",
                    "The exact runtime completion-query callable is absent from "
                    "the lease.",
                )
            try:
                status = stream_query(ctypes.c_void_p(stream_value))
            except Exception as exc:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_query_failed",
                    f"hipStreamQuery raised {type(exc).__name__}.",
                ) from exc
            if type(status) is not int:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_query_failed",
                    "hipStreamQuery returned a non-exact status value.",
                )
            if status == 0:
                return True
            if status == _HIP_ERROR_NOT_READY:
                return False
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_checkpoint_query_failed",
                "hipStreamQuery failed with an unrecognized status: "
                f"{_runtime_error_string(witness.loaded_runtime, status)}.",
            )

    def _checkpoint_memset_zero(
        self,
        token: object,
        stream: Any,
        base: Any,
        byte_length: int,
        *,
        _checkpoint_audit_descriptor_hash: str | None = None,
    ) -> None:
        """Queue one exact-runtime device memset under checkpoint ownership."""

        if type(byte_length) is not int or byte_length <= 0:
            raise _launch_contract_error(
                "checkpoint memset byte_length must be a positive exact int."
            )
        size_t_max = (1 << (8 * ctypes.sizeof(ctypes.c_size_t))) - 1
        if byte_length > size_t_max:
            raise _launch_contract_error(
                "checkpoint memset byte_length exceeds native size_t."
            )
        base_value = _runtime_pointer(base, "base")
        stream_value = _runtime_pointer(stream, "stream")
        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_access(token)
            if self._pending_streams and stream_value not in self._pending_streams:
                raise _launch_contract_error(
                    "all pending FGMRES v2 recurrence work must remain on the "
                    "first bound stream until its observed completion fence."
                )
            witness = self._validated_binding()
            _require_expected_device_ordinal(
                witness,
                operation="FGMRES v2 checkpoint memset",
                launch_disposition="not_attempted",
            )
            memset_async = witness.memset_async_callable
            if memset_async is None:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_memset_unavailable",
                    "The sealed hipMemsetAsync callable is unavailable.",
                    launch_disposition="not_attempted",
                )
            self._pending_streams[stream_value] = (
                self._pending_streams.get(stream_value, 0) + 1
            )
            descriptor_hash = _checkpoint_audit_descriptor_hash
            if descriptor_hash is None:
                descriptor_hash = _fallback_descriptor_hash_v1(
                    "memset",
                    "FGMRES v2 checkpoint memset",
                )
            ticket = witness.launch_fence_ledger_state.begin(
                "memset",
                descriptor_hash,
            )
            try:
                status = memset_async(
                    ctypes.c_void_p(base_value),
                    ctypes.c_int(0),
                    ctypes.c_size_t(byte_length),
                    ctypes.c_void_p(stream_value),
                )
            except BaseException as exc:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="ambiguous",
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_memset_failed",
                    f"hipMemsetAsync raised {type(exc).__name__}.",
                    launch_disposition="ambiguous",
                ) from exc
            if type(status) is not int:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="ambiguous",
                )
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_memset_failed",
                    "hipMemsetAsync returned a non-exact status value.",
                    launch_disposition="ambiguous",
                )
            if status != 0:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="rejected",
                )
                pending_count = self._pending_streams[stream_value] - 1
                if pending_count:
                    self._pending_streams[stream_value] = pending_count
                else:
                    del self._pending_streams[stream_value]
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_memset_failed",
                    "hipMemsetAsync failed: "
                    f"{_runtime_error_string(witness.loaded_runtime, status)}.",
                    launch_disposition="rejected",
                )
            witness.launch_fence_ledger_state.finish(
                ticket,
                disposition="success",
            )

    def _launch(
        self,
        function_name: str,
        *,
        stream: Any,
        grid_x: int,
        block_x: int,
        arguments: tuple[Any, ...],
        operation: str,
        checkpoint_owner_token: object | None,
        checkpoint_expected_prior_pending_count: int | None,
        checkpoint_audit_descriptor_hash: str | None,
    ) -> None:
        with self._checkpoint_owner_lock:
            self._require_open()
            self._require_checkpoint_owner_access(checkpoint_owner_token)
            stream_value = _runtime_pointer(stream, "stream")
            _require_expected_prior_pending_count(
                self._pending_streams,
                stream_pointer=stream_value,
                expected_count=checkpoint_expected_prior_pending_count,
            )
            if self._pending_streams and stream_value not in self._pending_streams:
                raise _launch_contract_error(
                    "all pending FGMRES v2 recurrence work must remain on the "
                    "first bound stream until its observed completion fence."
                )
            parameters = (ctypes.c_void_p * len(arguments))(
                *(
                    ctypes.cast(ctypes.byref(argument), ctypes.c_void_p)
                    for argument in arguments
                )
            )
            witness = self._validated_binding()
            function_pointer = next(
                (
                    pointer
                    for name, pointer in witness.function_pointers
                    if name == function_name
                ),
                None,
            )
            if function_pointer is None:
                raise _launch_contract_error(
                    f"fixed function binding {function_name!r} is unavailable."
                )
            _require_expected_device_ordinal(
                witness,
                operation=operation,
                launch_disposition="not_attempted",
            )
            self._pending_streams[stream_value] = (
                self._pending_streams.get(stream_value, 0) + 1
            )
            descriptor_hash = checkpoint_audit_descriptor_hash
            if descriptor_hash is None:
                descriptor_hash = _fallback_descriptor_hash_v1(
                    "launch",
                    operation,
                )
            ticket = witness.launch_fence_ledger_state.begin(
                "launch",
                descriptor_hash,
            )
            try:
                status = witness.launch_callable(
                    ctypes.c_void_p(function_pointer),
                    grid_x,
                    1,
                    1,
                    block_x,
                    1,
                    1,
                    0,
                    ctypes.c_void_p(stream_value),
                    parameters,
                    None,
                )
            except BaseException as exc:
                # An exception leaves launch acceptance ambiguous.  Ownership
                # remains pending until a real completion fence is observed.
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="ambiguous",
                )
                if not isinstance(exc, Exception):
                    raise
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_kernel_launch_failed",
                    f"{operation} hipModuleLaunchKernel raised {type(exc).__name__}.",
                    launch_disposition="ambiguous",
                ) from exc
            if type(status) is not int:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="ambiguous",
                )
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_kernel_launch_failed",
                    f"{operation} hipModuleLaunchKernel returned a non-exact "
                    "status value.",
                    launch_disposition="ambiguous",
                )
            if status != 0:
                witness.launch_fence_ledger_state.finish(
                    ticket,
                    disposition="rejected",
                )
                pending_count = self._pending_streams[stream_value] - 1
                if pending_count:
                    self._pending_streams[stream_value] = pending_count
                else:
                    del self._pending_streams[stream_value]
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_kernel_launch_failed",
                    f"{operation} hipModuleLaunchKernel failed: "
                    f"{_runtime_error_string(witness.loaded_runtime, status)}.",
                    launch_disposition="rejected",
                )
            witness.launch_fence_ledger_state.finish(
                ticket,
                disposition="success",
            )

    def _require_checkpoint_owner_identity(self, token: object) -> None:
        if token is not self._checkpoint_owner_token:
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_checkpoint_lease_token_invalid",
                "The exclusive checkpoint lease token is stale or foreign.",
            )

    def _require_checkpoint_owner_access(
        self,
        token: object | None,
        *,
        allow_poisoned: bool = False,
    ) -> None:
        owner = self._checkpoint_owner_token
        if owner is None:
            if token is not None:
                raise HipRtcFgmresV2Error(
                    "hip_rtc_fgmres_v2_checkpoint_lease_token_invalid",
                    "No checkpoint lease is active for the supplied token.",
                )
            return
        self._require_checkpoint_owner_identity(token)
        if self._checkpoint_owner_poisoned and not allow_poisoned:
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_checkpoint_lease_poisoned",
                "The checkpoint lease is poisoned and cannot enqueue more work.",
            )

    def _require_open(self) -> None:
        if (
            self._closed
            or self._unload_disposition != "live"
            or self._ownership_cell.owner is not self
        ):
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_kernel_closed",
                "HIPRTC FGMRES v2 kernel is closed or retiring.",
            )


def reduction_output_count_v2(value_count: int) -> int:
    """Return the exact number of 512-value partials for one stage."""

    checked = _positive_int32(value_count, "value_count")
    return (
        checked + HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK - 1
    ) // HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK


def reduction_stage_output_counts_v2(value_count: int) -> tuple[int, ...]:
    """Return first and all combine-stage output counts through one scalar."""

    count = reduction_output_count_v2(value_count)
    stages = [count]
    while count > 1:
        count = reduction_output_count_v2(count)
        stages.append(count)
    return tuple(stages)


def initial_reduction_launches_v2(
    free_dof_count: int,
) -> tuple[FgmresV2InitialReductionLaunch, ...]:
    """Plan the four ordered RHS/residual reduction trees for this slice."""

    n = _positive_int32(free_dof_count, "free_dof_count")
    stage_outputs = reduction_stage_output_counts_v2(n)
    stage_count = len(stage_outputs)
    rows: list[FgmresV2InitialReductionLaunch] = []
    metrics = (
        (
            "rhs_l2",
            _REDUCTION_MODES["LASSQ_LOAD"],
            _REDUCTION_MODES["COMBINE_LASSQ"],
            _REDUCTION_TARGETS["RHS_L2"],
        ),
        (
            "rhs_linf",
            _REDUCTION_MODES["LINF_LOAD"],
            _REDUCTION_MODES["COMBINE_MAX"],
            _REDUCTION_TARGETS["RHS_LINF"],
        ),
        (
            "initial_l2",
            _REDUCTION_MODES["LASSQ_TRUE_RESIDUAL"],
            _REDUCTION_MODES["COMBINE_LASSQ"],
            _REDUCTION_TARGETS["INITIAL_L2"],
        ),
        (
            "initial_linf",
            _REDUCTION_MODES["LINF_TRUE_RESIDUAL"],
            _REDUCTION_MODES["COMBINE_MAX"],
            _REDUCTION_TARGETS["INITIAL_LINF"],
        ),
    )
    for group, (metric, first_mode, combine_mode, final_target) in enumerate(metrics):
        input_count = n
        for stage, output_count in enumerate(stage_outputs):
            epoch = group * stage_count + stage
            rows.append(
                FgmresV2InitialReductionLaunch(
                    metric=metric,
                    reduction_mode=first_mode if stage == 0 else combine_mode,
                    reduction_target=(
                        final_target
                        if output_count == 1
                        else _REDUCTION_TARGETS["NONE"]
                    ),
                    expected_schedule_epoch=(2 + epoch if group < 2 else 6 + epoch),
                    expected_reduction_epoch=epoch,
                    value_count=input_count,
                    output_count=output_count,
                    final_stage=output_count == 1,
                )
            )
            input_count = output_count
    return tuple(rows)


def first_column_reduction_launches_v2(
    free_dof_count: int,
) -> tuple[FgmresV2FirstColumnReductionLaunch, ...]:
    """Plan the exact work, row-zero dot, and after-first reduction trees.

    The returned rows cover only restart one, column zero and end immediately
    before ``CONTROL_DGKS_DECIDE_PASS0``.  They are a concrete expansion of
    :func:`hip_fgmres_first_column_partial_schedule_payload_v2` for one ``F``.
    """

    n = _positive_int32(free_dof_count, "free_dof_count")
    stage_outputs = reduction_stage_output_counts_v2(n)
    stage_count = len(stage_outputs)
    rows: list[FgmresV2FirstColumnReductionLaunch] = []
    groups = (
        (
            "work_before",
            _REDUCTION_MODES["LASSQ_WORK_W"],
            _REDUCTION_MODES["COMBINE_LASSQ"],
            _REDUCTION_TARGETS["WORK_BEFORE"],
            4 * stage_count,
            13,
        ),
        (
            "dot_first_pass_row0",
            _REDUCTION_MODES["DOT_W_VI"],
            _REDUCTION_MODES["COMBINE_SUM"],
            _REDUCTION_TARGETS["DOT"],
            5 * stage_count,
            13,
        ),
        (
            "after_first",
            _REDUCTION_MODES["LASSQ_WORK_W"],
            _REDUCTION_MODES["COMBINE_LASSQ"],
            _REDUCTION_TARGETS["AFTER_FIRST"],
            6 * stage_count,
            15,
        ),
    )
    for (
        metric,
        first_mode,
        combine_mode,
        final_target,
        epoch_base,
        schedule_base,
    ) in groups:
        input_count = n
        for stage, output_count in enumerate(stage_outputs):
            epoch = epoch_base + stage
            rows.append(
                FgmresV2FirstColumnReductionLaunch(
                    metric=metric,
                    reduction_mode=first_mode if stage == 0 else combine_mode,
                    reduction_target=(
                        final_target
                        if output_count == 1
                        else _REDUCTION_TARGETS["NONE"]
                    ),
                    expected_schedule_epoch=schedule_base + epoch,
                    expected_restart=1,
                    expected_column=0,
                    expected_reduction_epoch=epoch,
                    value_count=input_count,
                    output_count=output_count,
                    logical_index=0,
                    final_stage=output_count == 1,
                )
            )
            input_count = output_count
    return tuple(rows)


def first_column_completion_launches_v2(
    free_dof_count: int,
) -> tuple[FgmresV2FirstColumnCompletionLaunch, ...]:
    """Expand the flag-independent continuation through column-zero Givens.

    Every caller must submit every returned row in order.  In particular, the
    second DOT tree, its accept, and the second MGS row are never removed when
    DGKS is false; those fixed kernels claim their epochs as device-side
    gated no-ops.
    """

    _validated_completion_schedule(
        _kernel_abi(),
        code="hip_rtc_fgmres_v2_completion_schedule_invalid",
    )
    n = _positive_int32(free_dof_count, "free_dof_count")
    stage_outputs = reduction_stage_output_counts_v2(n)
    stages = len(stage_outputs)
    rows: list[FgmresV2FirstColumnCompletionLaunch] = []

    input_count = n
    for stage, output_count in enumerate(stage_outputs):
        final = output_count == 1
        epoch = 7 * stages + stage
        rows.append(
            FgmresV2FirstColumnCompletionLaunch(
                name="REDUCE_DOT_SECOND_PASS_ROW0",
                submission_kind="reduction",
                kernel_symbol=HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                mode=(
                    _REDUCTION_MODES["DOT_W_VI"]
                    if stage == 0
                    else _REDUCTION_MODES["COMBINE_SUM"]
                ),
                expected_schedule_epoch=16 + epoch,
                expected_restart=1,
                expected_column=0,
                logical_index=0,
                row_index=None,
                pass_index=None,
                vector_gate=None,
                reduction_target=(
                    _REDUCTION_TARGETS["DOT"] if final else _REDUCTION_TARGETS["NONE"]
                ),
                expected_reduction_epoch=epoch,
                value_count=input_count,
                output_count=output_count,
                final_stage=final,
                device_gate_source="dgks_reorth_required",
            )
        )
        input_count = output_count

    rows.extend(
        (
            FgmresV2FirstColumnCompletionLaunch(
                name="CONTROL_DOT_ACCEPT_ROW0_PASS1",
                submission_kind="control",
                kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                mode=_CONTROL_MODES["DOT_ACCEPT"],
                expected_schedule_epoch=16 + 8 * stages,
                expected_restart=1,
                expected_column=0,
                logical_index=None,
                row_index=0,
                pass_index=1,
                vector_gate=None,
                reduction_target=None,
                expected_reduction_epoch=None,
                value_count=None,
                output_count=None,
                final_stage=None,
                device_gate_source="dgks_reorth_required",
            ),
            FgmresV2FirstColumnCompletionLaunch(
                name="VECTOR_MGS_SUBTRACT_ROW0_PASS1",
                submission_kind="vector",
                kernel_symbol=HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                mode=_VECTOR_MODES["MGS_SUBTRACT_INDEXED"],
                expected_schedule_epoch=17 + 8 * stages,
                expected_restart=1,
                expected_column=0,
                logical_index=0,
                row_index=None,
                pass_index=None,
                vector_gate=_VECTOR_GATES["DGKS_SECOND_PASS"],
                reduction_target=None,
                expected_reduction_epoch=None,
                value_count=None,
                output_count=None,
                final_stage=None,
                device_gate_source="dgks_reorth_required",
            ),
        )
    )

    input_count = n
    for stage, output_count in enumerate(stage_outputs):
        final = output_count == 1
        epoch = 8 * stages + stage
        rows.append(
            FgmresV2FirstColumnCompletionLaunch(
                name="REDUCE_H_NEXT",
                submission_kind="reduction",
                kernel_symbol=HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                mode=(
                    _REDUCTION_MODES["LASSQ_WORK_W"]
                    if stage == 0
                    else _REDUCTION_MODES["COMBINE_LASSQ"]
                ),
                expected_schedule_epoch=18 + epoch,
                expected_restart=1,
                expected_column=0,
                logical_index=0,
                row_index=None,
                pass_index=None,
                vector_gate=None,
                reduction_target=(
                    _REDUCTION_TARGETS["H_NEXT"]
                    if final
                    else _REDUCTION_TARGETS["NONE"]
                ),
                expected_reduction_epoch=epoch,
                value_count=input_count,
                output_count=output_count,
                final_stage=final,
                device_gate_source=None,
            )
        )
        input_count = output_count

    rows.extend(
        (
            FgmresV2FirstColumnCompletionLaunch(
                name="VECTOR_NORMALIZE_V1",
                submission_kind="vector",
                kernel_symbol=HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                mode=_VECTOR_MODES["NORMALIZE_V_NEXT"],
                expected_schedule_epoch=18 + 9 * stages,
                expected_restart=1,
                expected_column=0,
                logical_index=1,
                row_index=None,
                pass_index=None,
                vector_gate=_VECTOR_GATES["ACTIVE"],
                reduction_target=None,
                expected_reduction_epoch=None,
                value_count=None,
                output_count=None,
                final_stage=None,
                device_gate_source=None,
            ),
            FgmresV2FirstColumnCompletionLaunch(
                name="CONTROL_ARNOLDI_GIVENS_COLUMN0",
                submission_kind="control",
                kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                mode=_CONTROL_MODES["ARNOLDI_GIVENS"],
                expected_schedule_epoch=19 + 9 * stages,
                expected_restart=1,
                expected_column=0,
                logical_index=None,
                row_index=-1,
                pass_index=-1,
                vector_gate=None,
                reduction_target=None,
                expected_reduction_epoch=None,
                value_count=None,
                output_count=None,
                final_stage=None,
                device_gate_source=None,
            ),
        )
    )
    return tuple(rows)


def first_column_candidate_preparation_launches_v2(
    free_dof_count: int,
) -> tuple[FgmresV2FirstColumnCandidatePreparationLaunch, ...]:
    """Expand the flag-independent prefix through candidate vector accept.

    The returned tuple always contains back substitution, trial-vector build,
    every solution-update reduction stage, and vector accept.  Candidate and
    triangular-breakdown state is consumed only by package-owned device code;
    callers cannot branch or omit rows through this API.
    """

    _validated_candidate_preparation_schedule(
        _kernel_abi(),
        code="hip_rtc_fgmres_v2_candidate_preparation_schedule_invalid",
    )
    n = _positive_int32(free_dof_count, "free_dof_count")
    stage_outputs = reduction_stage_output_counts_v2(n)
    stages = len(stage_outputs)
    rows: list[FgmresV2FirstColumnCandidatePreparationLaunch] = [
        FgmresV2FirstColumnCandidatePreparationLaunch(
            name="CONTROL_BACKSUBSTITUTE_COLUMN0",
            submission_kind="control",
            kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
            mode=_CONTROL_MODES["BACKSUBSTITUTE"],
            expected_schedule_epoch=20 + 9 * stages,
            expected_restart=1,
            expected_column=0,
            logical_index=None,
            row_index=-1,
            pass_index=-1,
            vector_gate=None,
            reduction_target=None,
            expected_reduction_epoch=None,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source="candidate_required",
        ),
        FgmresV2FirstColumnCandidatePreparationLaunch(
            name="VECTOR_BUILD_TRIAL_X_COLUMN0",
            submission_kind="vector",
            kernel_symbol=HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
            mode=_VECTOR_MODES["BUILD_TRIAL_X"],
            expected_schedule_epoch=21 + 9 * stages,
            expected_restart=1,
            expected_column=0,
            logical_index=0,
            row_index=None,
            pass_index=None,
            vector_gate=_VECTOR_GATES["CANDIDATE_REQUIRED"],
            reduction_target=None,
            expected_reduction_epoch=None,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source=("candidate_required_and_not_triangular_breakdown"),
        ),
    ]

    input_count = n
    for stage, output_count in enumerate(stage_outputs):
        final = output_count == 1
        epoch = 9 * stages + stage
        rows.append(
            FgmresV2FirstColumnCandidatePreparationLaunch(
                name="REDUCE_SOLUTION_UPDATE_L2_COLUMN0",
                submission_kind="reduction",
                kernel_symbol=HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                mode=(
                    _REDUCTION_MODES["LASSQ_WORK_W_MINUS_X"]
                    if stage == 0
                    else _REDUCTION_MODES["COMBINE_LASSQ"]
                ),
                expected_schedule_epoch=22 + epoch,
                expected_restart=1,
                expected_column=0,
                logical_index=0,
                row_index=None,
                pass_index=None,
                vector_gate=None,
                reduction_target=(
                    _REDUCTION_TARGETS["UPDATE_L2"]
                    if final
                    else _REDUCTION_TARGETS["NONE"]
                ),
                expected_reduction_epoch=epoch,
                value_count=input_count,
                output_count=output_count,
                final_stage=final,
                device_gate_source=("candidate_required_and_not_triangular_breakdown"),
            )
        )
        input_count = output_count

    rows.append(
        FgmresV2FirstColumnCandidatePreparationLaunch(
            name="CONTROL_VECTOR_ACCEPT_TRIAL_COLUMN0",
            submission_kind="control",
            kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
            mode=_CONTROL_MODES["VECTOR_ACCEPT"],
            expected_schedule_epoch=22 + 10 * stages,
            expected_restart=1,
            expected_column=0,
            logical_index=None,
            row_index=-1,
            pass_index=-1,
            vector_gate=None,
            reduction_target=None,
            expected_reduction_epoch=None,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source=("candidate_required_and_not_triangular_breakdown"),
        )
    )
    return tuple(rows)


def first_column_candidate_residual_launches_v2(
    free_dof_count: int,
    restart_dimension: int,
) -> tuple[FgmresV2FirstColumnCandidateResidualLaunch, ...]:
    """Expand candidate SpMV and raw residual metrics without host branching.

    ``restart_dimension`` fixes the allocation-base logical index ``M`` in
    every V[M] row.  Raw launch wrappers preserve their device ABI signatures:
    they bound a candidate index to ``1..16``, while the device control state
    performs the final equality check against its initialized ``M``.
    """

    _validated_candidate_residual_schedule(
        _kernel_abi(),
        code="hip_rtc_fgmres_v2_candidate_residual_schedule_invalid",
    )
    n = _positive_int32(free_dof_count, "free_dof_count")
    restart = _bounded_int(
        restart_dimension,
        "restart_dimension",
        minimum=1,
        maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
    )
    stage_outputs = reduction_stage_output_counts_v2(n)
    stages = len(stage_outputs)
    active = "candidate_required_and_not_triangular_breakdown"
    rows: list[FgmresV2FirstColumnCandidateResidualLaunch] = [
        FgmresV2FirstColumnCandidateResidualLaunch(
            name="SPMV_CANDIDATE_COLUMN0",
            submission_kind="spmv",
            kernel_symbol=HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL,
            mode=_SPMV_MODES["CANDIDATE"],
            expected_schedule_epoch=23 + 10 * stages,
            expected_restart=1,
            expected_column=0,
            logical_index=restart,
            row_index=None,
            pass_index=None,
            vector_gate=None,
            reduction_target=None,
            expected_reduction_epoch=None,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source=active,
        ),
        FgmresV2FirstColumnCandidateResidualLaunch(
            name="CONTROL_OPERATOR_ACCEPT_CANDIDATE_COLUMN0",
            submission_kind="control",
            kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
            mode=_CONTROL_MODES["OPERATOR_ACCEPT"],
            expected_schedule_epoch=24 + 10 * stages,
            expected_restart=1,
            expected_column=0,
            logical_index=None,
            row_index=-1,
            pass_index=-1,
            vector_gate=None,
            reduction_target=None,
            expected_reduction_epoch=None,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source=active,
        ),
        FgmresV2FirstColumnCandidateResidualLaunch(
            name="VECTOR_FORM_CANDIDATE_RESIDUAL_COLUMN0",
            submission_kind="vector",
            kernel_symbol=HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
            mode=_VECTOR_MODES["FORM_CANDIDATE_RESIDUAL"],
            expected_schedule_epoch=25 + 10 * stages,
            expected_restart=1,
            expected_column=0,
            logical_index=restart,
            row_index=None,
            pass_index=None,
            vector_gate=_VECTOR_GATES["CANDIDATE_REQUIRED"],
            reduction_target=None,
            expected_reduction_epoch=None,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source=active,
        ),
    ]

    groups = (
        (
            "REDUCE_CANDIDATE_L2_COLUMN0",
            _REDUCTION_MODES["LASSQ_V_M"],
            _REDUCTION_MODES["COMBINE_LASSQ"],
            _REDUCTION_TARGETS["CANDIDATE_L2"],
            10 * stages,
        ),
        (
            "REDUCE_CANDIDATE_LINF_COLUMN0",
            _REDUCTION_MODES["LINF_V_M"],
            _REDUCTION_MODES["COMBINE_MAX"],
            _REDUCTION_TARGETS["CANDIDATE_LINF"],
            11 * stages,
        ),
    )
    for name, first_mode, combine_mode, final_target, epoch_base in groups:
        input_count = n
        for stage, output_count in enumerate(stage_outputs):
            final = output_count == 1
            epoch = epoch_base + stage
            rows.append(
                FgmresV2FirstColumnCandidateResidualLaunch(
                    name=name,
                    submission_kind="reduction",
                    kernel_symbol=HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                    mode=first_mode if stage == 0 else combine_mode,
                    expected_schedule_epoch=26 + epoch,
                    expected_restart=1,
                    expected_column=0,
                    logical_index=restart,
                    row_index=None,
                    pass_index=None,
                    vector_gate=None,
                    reduction_target=(
                        final_target if final else _REDUCTION_TARGETS["NONE"]
                    ),
                    expected_reduction_epoch=epoch,
                    value_count=input_count,
                    output_count=output_count,
                    final_stage=final,
                    device_gate_source=active,
                )
            )
            input_count = output_count
    return tuple(rows)


def first_column_candidate_scale_metrics_launches_v2(
    free_dof_count: int,
) -> tuple[FgmresV2FirstColumnCandidateScaleMetricsLaunch, ...]:
    """Expand the predicate-independent trial and committed L2 trees."""

    _validated_candidate_scale_metrics_schedule(
        _kernel_abi(),
        code="hip_rtc_fgmres_v2_candidate_scale_metrics_schedule_invalid",
    )
    n = _positive_int32(free_dof_count, "free_dof_count")
    stage_outputs = reduction_stage_output_counts_v2(n)
    stages = len(stage_outputs)
    rows: list[FgmresV2FirstColumnCandidateScaleMetricsLaunch] = []
    groups = (
        (
            "REDUCE_TRIAL_X_L2_COLUMN0",
            _REDUCTION_MODES["LASSQ_WORK_W"],
            _REDUCTION_MODES["COMBINE_LASSQ"],
            _REDUCTION_TARGETS["TRIAL_X_L2"],
            12 * stages,
        ),
        (
            "REDUCE_COMMITTED_X_L2_COLUMN0",
            _REDUCTION_MODES["LASSQ_SOLUTION_X"],
            _REDUCTION_MODES["COMBINE_LASSQ"],
            _REDUCTION_TARGETS["COMMITTED_X_L2"],
            13 * stages,
        ),
    )
    for name, first_mode, combine_mode, final_target, epoch_base in groups:
        input_count = n
        for stage, output_count in enumerate(stage_outputs):
            final = output_count == 1
            epoch = epoch_base + stage
            rows.append(
                FgmresV2FirstColumnCandidateScaleMetricsLaunch(
                    name=name,
                    submission_kind="reduction",
                    kernel_symbol=HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                    mode=first_mode if stage == 0 else combine_mode,
                    expected_schedule_epoch=26 + epoch,
                    expected_restart=1,
                    expected_column=0,
                    logical_index=0,
                    row_index=None,
                    pass_index=None,
                    vector_gate=None,
                    reduction_target=(
                        final_target if final else _REDUCTION_TARGETS["NONE"]
                    ),
                    expected_reduction_epoch=epoch,
                    value_count=input_count,
                    output_count=output_count,
                    final_stage=final,
                    device_gate_source="scale_metrics_required",
                )
            )
            input_count = output_count
    return tuple(rows)


def first_column_checkpoint_transaction_launches_v2(
    free_dof_count: int,
    restart_dimension: int,
) -> tuple[FgmresV2FirstColumnCheckpointTransactionLaunch, ...]:
    """Return the fixed decide, preflight, commit, and finalize transaction."""

    _validated_checkpoint_transaction_schedule(
        _kernel_abi(),
        code="hip_rtc_fgmres_v2_checkpoint_transaction_schedule_invalid",
    )
    n = _positive_int32(free_dof_count, "free_dof_count")
    restart = _bounded_int(
        restart_dimension,
        "restart_dimension",
        minimum=1,
        maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
    )
    stages = len(reduction_stage_output_counts_v2(n))
    reduction_epoch = 14 * stages
    return (
        FgmresV2FirstColumnCheckpointTransactionLaunch(
            name="CHECKPOINT_DECIDE_COLUMN0",
            submission_kind="control",
            kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
            mode=_CONTROL_MODES["CHECKPOINT_DECIDE"],
            expected_schedule_epoch=26 + reduction_epoch,
            expected_restart=1,
            expected_column=0,
            logical_index=None,
            row_index=-1,
            pass_index=-1,
            vector_gate=None,
            reduction_target=None,
            expected_reduction_epoch=reduction_epoch,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source="always",
        ),
        FgmresV2FirstColumnCheckpointTransactionLaunch(
            name="PREFLIGHT_COMMIT_SOURCE_COLUMN0",
            submission_kind="vector",
            kernel_symbol=HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
            mode=_VECTOR_MODES["PREFLIGHT_COMMIT_SOURCE"],
            expected_schedule_epoch=27 + reduction_epoch,
            expected_restart=1,
            expected_column=0,
            logical_index=restart,
            row_index=None,
            pass_index=None,
            vector_gate=_VECTOR_GATES["COMMIT_REQUIRED"],
            reduction_target=None,
            expected_reduction_epoch=reduction_epoch,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source="commit_required",
        ),
        FgmresV2FirstColumnCheckpointTransactionLaunch(
            name="COMMIT_CHECKPOINT_COLUMN0",
            submission_kind="vector",
            kernel_symbol=HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
            mode=_VECTOR_MODES["COMMIT_CHECKPOINT"],
            expected_schedule_epoch=27 + reduction_epoch,
            expected_restart=1,
            expected_column=0,
            logical_index=restart,
            row_index=None,
            pass_index=None,
            vector_gate=_VECTOR_GATES["COMMIT_REQUIRED"],
            reduction_target=None,
            expected_reduction_epoch=reduction_epoch,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source="commit_required",
        ),
        FgmresV2FirstColumnCheckpointTransactionLaunch(
            name="CHECKPOINT_FINALIZE_COLUMN0",
            submission_kind="control",
            kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
            mode=_CONTROL_MODES["CHECKPOINT_FINALIZE"],
            expected_schedule_epoch=28 + reduction_epoch,
            expected_restart=1,
            expected_column=0,
            logical_index=None,
            row_index=-1,
            pass_index=-1,
            vector_gate=None,
            reduction_target=None,
            expected_reduction_epoch=reduction_epoch,
            value_count=None,
            output_count=None,
            final_stage=None,
            device_gate_source="always",
        ),
    )


def first_column_predecessor_validation_launch_v2(
    free_dof_count: int,
) -> FgmresV2FirstColumnPredecessorValidationLaunch:
    """Return the single non-advancing first-column device seal launch."""

    _validated_predecessor_validation_schedule(
        _kernel_abi(),
        code="hip_rtc_fgmres_v2_predecessor_validation_schedule_invalid",
    )
    n = _positive_int32(free_dof_count, "free_dof_count")
    stages = len(reduction_stage_output_counts_v2(n))
    reduction_epoch = 14 * stages
    return FgmresV2FirstColumnPredecessorValidationLaunch(
        name="PREDECESSOR_VALIDATE_COLUMN0",
        submission_kind="control",
        kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
        mode=_CONTROL_MODES["PREDECESSOR_VALIDATE"],
        expected_schedule_epoch=26 + reduction_epoch,
        expected_restart=1,
        expected_column=0,
        row_index=-1,
        pass_index=-1,
        expected_reduction_epoch=reduction_epoch,
        admitted_mask_domain=(0, 1792, 7936),
        schedule_epoch_advances=False,
        reduction_epoch_advances=False,
    )


def canonical_first_column_predecessor_launches_v2(
    free_dof_count: int,
    restart_dimension: int,
) -> tuple[FgmresV2CanonicalPredecessorLaunch, ...]:
    """Return every fixed kernel row from INIT through the device seal.

    The host receives no live gate input.  Conditional numerical work remains
    device-gated while all rows are always present in one deterministic tuple.
    """

    n = _positive_int32(free_dof_count, "free_dof_count")
    restart = _bounded_int(
        restart_dimension,
        "restart_dimension",
        minimum=1,
        maximum=HIP_FGMRES_MAX_RESTART_DIMENSION,
    )
    stages = len(reduction_stage_output_counts_v2(n))
    boundary = 7 + 4 * stages
    rows: list[FgmresV2CanonicalPredecessorLaunch] = []

    def control(
        name: str,
        mode_name: str,
        epoch: int,
        expected_restart: int,
        expected_column: int,
        row_index: int = -1,
        pass_index: int = -1,
    ) -> None:
        rows.append(
            FgmresV2CanonicalPredecessorLaunch(
                name=name,
                submission_kind="control",
                kernel_symbol=HIP_RTC_FGMRES_V2_CONTROL_SYMBOL,
                mode=_CONTROL_MODES[mode_name],
                expected_schedule_epoch=epoch,
                expected_restart=expected_restart,
                expected_column=expected_column,
                row_index=row_index,
                pass_index=pass_index,
                device_gate_source="always",
            )
        )

    def vector(
        name: str,
        mode_name: str,
        gate_name: str,
        epoch: int,
        expected_restart: int,
        expected_column: int,
        logical_index: int,
        device_gate_source: str,
    ) -> None:
        rows.append(
            FgmresV2CanonicalPredecessorLaunch(
                name=name,
                submission_kind="vector",
                kernel_symbol=HIP_RTC_FGMRES_V2_VECTOR_SYMBOL,
                mode=_VECTOR_MODES[mode_name],
                expected_schedule_epoch=epoch,
                expected_restart=expected_restart,
                expected_column=expected_column,
                logical_index=logical_index,
                vector_gate=_VECTOR_GATES[gate_name],
                device_gate_source=device_gate_source,
            )
        )

    def spmv(
        name: str,
        mode_name: str,
        epoch: int,
        expected_restart: int,
        expected_column: int,
        logical_index: int,
        device_gate_source: str,
    ) -> None:
        rows.append(
            FgmresV2CanonicalPredecessorLaunch(
                name=name,
                submission_kind="spmv",
                kernel_symbol=HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL,
                mode=_SPMV_MODES[mode_name],
                expected_schedule_epoch=epoch,
                expected_restart=expected_restart,
                expected_column=expected_column,
                logical_index=logical_index,
                device_gate_source=device_gate_source,
            )
        )

    metric_stages: dict[str, int] = {}

    reduction_phase = "initial"

    def reduction(row: Any) -> None:
        stage = metric_stages.get(row.metric, 0)
        rows.append(
            FgmresV2CanonicalPredecessorLaunch(
                name=f"REDUCE_{row.metric.upper()}_{stage}",
                submission_kind="reduction",
                kernel_symbol=HIP_RTC_FGMRES_V2_REDUCE_SYMBOL,
                mode=row.reduction_mode,
                expected_schedule_epoch=row.expected_schedule_epoch,
                expected_restart=getattr(row, "expected_restart", -1),
                expected_column=getattr(row, "expected_column", -1),
                logical_index=getattr(row, "logical_index", 0),
                reduction_target=row.reduction_target,
                expected_reduction_epoch=row.expected_reduction_epoch,
                value_count=row.value_count,
                output_count=row.output_count,
                final_stage=row.final_stage,
                device_gate_source=getattr(row, "device_gate_source", None),
                reduction_tree_id=f"{reduction_phase}:{row.metric}",
            )
        )
        metric_stages[row.metric] = stage + 1

    def planned(row: Any) -> None:
        rows.append(
            FgmresV2CanonicalPredecessorLaunch(
                name=row.name,
                submission_kind=row.submission_kind,
                kernel_symbol=row.kernel_symbol,
                mode=row.mode,
                expected_schedule_epoch=row.expected_schedule_epoch,
                expected_restart=row.expected_restart,
                expected_column=row.expected_column,
                logical_index=row.logical_index,
                row_index=row.row_index,
                pass_index=row.pass_index,
                vector_gate=row.vector_gate,
                reduction_target=row.reduction_target,
                expected_reduction_epoch=row.expected_reduction_epoch,
                value_count=row.value_count,
                output_count=row.output_count,
                final_stage=row.final_stage,
                device_gate_source=row.device_gate_source,
                reduction_tree_id=(
                    row.name if row.submission_kind == "reduction" else None
                ),
            )
        )

    initial = initial_reduction_launches_v2(n)
    control("CONTROL_INIT", "INIT", 0, -1, -1)
    vector("COPY_INITIAL_X", "COPY_INITIAL_X", "ACTIVE", 1, -1, -1, 0, "active")
    for row in initial[: 2 * stages]:
        reduction(row)
    control("CONTROL_BIND_RHS", "BIND_RHS", 2 + 2 * stages, -1, -1)
    spmv("SPMV_INITIAL", "INITIAL", 3 + 2 * stages, -1, -1, 0, "active")
    control(
        "CONTROL_OPERATOR_ACCEPT_INITIAL", "OPERATOR_ACCEPT", 4 + 2 * stages, -1, -1
    )
    vector(
        "FORM_INITIAL_RESIDUAL",
        "FORM_INITIAL_RESIDUAL",
        "ACTIVE",
        5 + 2 * stages,
        -1,
        -1,
        0,
        "active",
    )
    for row in initial[2 * stages :]:
        reduction(row)
    control("CONTROL_INITIAL_GATE", "INITIAL_GATE", 6 + 4 * stages, -1, -1)

    metric_stages.clear()
    reduction_phase = "column"
    control("RESTART_BEGIN_COLUMN0", "RESTART_BEGIN", boundary, 1, -1)
    vector("NORMALIZE_V0", "NORMALIZE_V0", "ACTIVE", boundary + 1, 1, 0, 0, "active")
    vector(
        "APPLY_JACOBI_COLUMN0",
        "APPLY_JACOBI_INDEXED",
        "ACTIVE",
        boundary + 2,
        1,
        0,
        0,
        "active",
    )
    control("PRECONDITION_ACCEPT_COLUMN0", "PRECONDITION_ACCEPT", boundary + 3, 1, 0)
    spmv("SPMV_ARNOLDI_COLUMN0", "ARNOLDI", boundary + 4, 1, 0, 0, "active")
    control("OPERATOR_ACCEPT_COLUMN0", "OPERATOR_ACCEPT", boundary + 5, 1, 0)
    column = first_column_reduction_launches_v2(n)
    for row in column[: 2 * stages]:
        reduction(row)
    control("DOT_ACCEPT_COLUMN0_PASS0", "DOT_ACCEPT", 13 + 6 * stages, 1, 0, 0, 0)
    vector(
        "MGS_SUBTRACT_COLUMN0_PASS0",
        "MGS_SUBTRACT_INDEXED",
        "ACTIVE",
        14 + 6 * stages,
        1,
        0,
        0,
        "active",
    )
    for row in column[2 * stages :]:
        reduction(row)
    control("DGKS_DECIDE_COLUMN0", "DGKS_DECIDE", 15 + 7 * stages, 1, 0, -1, 0)

    for row in first_column_completion_launches_v2(n):
        planned(row)
    for row in first_column_candidate_preparation_launches_v2(n):
        planned(row)
    for row in first_column_candidate_residual_launches_v2(n, restart):
        planned(row)
    for row in first_column_candidate_scale_metrics_launches_v2(n):
        planned(row)
    validator = first_column_predecessor_validation_launch_v2(n)
    rows.append(
        FgmresV2CanonicalPredecessorLaunch(
            name=validator.name,
            submission_kind=validator.submission_kind,
            kernel_symbol=validator.kernel_symbol,
            mode=validator.mode,
            expected_schedule_epoch=validator.expected_schedule_epoch,
            expected_restart=validator.expected_restart,
            expected_column=validator.expected_column,
            row_index=validator.row_index,
            pass_index=validator.pass_index,
            expected_reduction_epoch=validator.expected_reduction_epoch,
            device_gate_source="active_checkpoint_predecessor",
        )
    )
    expected_count = 27 + 14 * stages
    if len(rows) != expected_count:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_canonical_predecessor_schedule_invalid",
            "The canonical predecessor launch count is internally inconsistent.",
        )
    return tuple(rows)


def solve_record_byte_length_v2(maximum_restart_count: int) -> int:
    """Return the exact public v2 solve-record byte extent."""

    checked = _bounded_int(
        maximum_restart_count,
        "maximum_restart_count",
        minimum=0,
        maximum=HIP_FGMRES_MAX_ITERATIONS,
    )
    record = _record_abi()
    return int(record["header_bytes"]) + int(record["restart_bytes"]) * checked


def compile_hip_rtc_fgmres_v2_kernel(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None = None,
) -> HipRtcFgmresV2Kernel:
    """Compile and load the package-owned four-symbol recurrence-v2 module."""

    try:
        frame = _KERNEL_HANDOFF.get()
        handoff = None if frame is None else frame.claim()
        direct_handoff = handoff is None
        if handoff is None:
            handoff = _HipRtcFgmresV2KernelHandoff()
        try:
            return _compile_v2_impl(
                loaded_runtime,
                architecture,
                hiprtc_library,
                _handoff=handoff,
            )
        except BaseException as primary:
            if direct_handoff:
                _recover_direct_fgmres_v2_compile_handoff(handoff, primary)
            raise
    except HipRtcFgmresV2Error:
        raise
    except HipRtcError as exc:
        raise HipRtcFgmresV2Error(
            exc.code,
            exc.message,
            compile_log=exc.compile_log,
        ) from exc
    except Exception as exc:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_unexpected_failure",
            f"Unexpected HIPRTC FGMRES v2 pipeline failure: {type(exc).__name__}.",
        ) from exc


def _recover_direct_fgmres_v2_compile_handoff(
    handoff: _HipRtcFgmresV2KernelHandoff,
    primary: BaseException,
) -> None:
    """Recover a direct compiler owner across its public return boundary."""

    owner = handoff.kernel
    if owner is None:
        return
    if (
        type(owner) is _HipRtcFgmresV2ModuleCleanupOwner
        and isinstance(primary, HipRtcFgmresV2Error)
        and primary.cleanup_owner is owner
    ):
        return
    if type(owner) is HipRtcFgmresV2Kernel:
        module_owner = owner._ownership_cell.preowner
        if type(module_owner) is not _HipRtcFgmresV2ModuleCleanupOwner:
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_module_ownership_invalid",
                "The direct compiler lost its exact preallocated module owner.",
            ) from primary
        _reclaim_fgmres_v2_module_ownership(module_owner, owner)
        owner = module_owner
    if type(owner) is _HipRtcFgmresV2ModuleCleanupOwner:
        _cleanup_loaded_module(
            owner,
            primary,
            compile_log=(
                primary.compile_log if isinstance(primary, HipRtcError) else ""
            ),
        )


def _compile_v2_with_handoff(
    compiler: Any,
    handoff: _HipRtcFgmresV2KernelHandoff,
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
) -> HipRtcFgmresV2Kernel:
    """Call the public v2 compiler under a task-local cleanup handoff."""

    if type(handoff) is not _HipRtcFgmresV2KernelHandoff or handoff.occupied:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_kernel_handoff_invalid",
            "An exact empty kernel handoff is required.",
        )
    frame = _HipRtcFgmresV2KernelHandoffFrame(handoff)
    isolated_context = copy_context()

    def invoke() -> HipRtcFgmresV2Kernel:
        _KERNEL_HANDOFF.set(frame)
        return compiler(loaded_runtime, architecture, hiprtc_library)

    try:
        return isolated_context.run(invoke)
    finally:
        # The caller's Context remains untouched across every interruption;
        # the private copy retains at most a one-shot weak route.
        frame.disarm()


def _compile_v2_impl(
    loaded_runtime: Any,
    architecture: str,
    hiprtc_library: str | Path | None,
    *,
    _handoff: _HipRtcFgmresV2KernelHandoff | None = None,
) -> HipRtcFgmresV2Kernel:
    if _handoff is not None and (
        type(_handoff) is not _HipRtcFgmresV2KernelHandoff or _handoff.occupied
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_kernel_handoff_invalid",
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
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_version_failed",
            f"hiprtcVersion failed: {rtc.error_string(status)}.",
        )
    if not callable(getattr(loaded_runtime, "hip_init", None)):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_runtime_invalid",
            "loaded_runtime does not expose hip_init().",
        )
    try:
        init_status = int(loaded_runtime.hip_init())
    except Exception as exc:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_runtime_init_failed",
            f"hipInit raised {type(exc).__name__}.",
        ) from exc
    if init_status != 0:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_runtime_init_failed",
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
    cleanup_owner = _HipRtcFgmresV2ModuleCleanupOwner._preallocated(
        runtime,
        module,
    )
    if _handoff is not None:
        _handoff.publish_module_owner(cleanup_owner)
    try:
        status = runtime.load_module_into(code_object, module)
        if status != 0 or not module.value:
            raise HipRtcFgmresV2Error(
                "hip_rtc_fgmres_v2_module_load_failed",
                f"hipModuleLoadData failed: {runtime.error_string(status)}.",
                compile_log=compile_log,
            )
        functions = {
            key: _required_function(runtime, module, symbol, compile_log)
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
        kernel = HipRtcFgmresV2Kernel(
            runtime=runtime,
            module=module,
            functions=functions,
            identity=identity,
            ownership_cell=cleanup_owner._ownership_cell,
            _owner_mint=_KERNEL_OWNER_MINT,
        )
        if _handoff is not None:
            _handoff.promote(cleanup_owner, kernel)
        else:
            _transfer_fgmres_v2_module_ownership(cleanup_owner, kernel)
        return kernel
    except BaseException as primary:
        if "kernel" in locals() and _handoff is not None and _handoff.kernel is kernel:
            raise
        reclaim_kernel = False
        with cleanup_owner._ownership_cell.lock:
            reclaim_kernel = (
                "kernel" in locals() and cleanup_owner._ownership_cell.owner is kernel
            )
        if reclaim_kernel:
            _reclaim_fgmres_v2_module_ownership(cleanup_owner, kernel)
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
    compile_log: str,
) -> ctypes.c_void_p:
    status, function = runtime.get_function(module, symbol)
    if status != 0 or not function.value:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_symbol_missing",
            f"hipModuleGetFunction failed for fixed symbol {symbol}: "
            f"{runtime.error_string(status)}.",
            compile_log=compile_log,
        )
    return function


def _cleanup_loaded_module(
    cleanup_owner: _HipRtcFgmresV2ModuleCleanupOwner,
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
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_module_cleanup_failed",
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
) -> HipRtcFgmresV2KernelIdentity:
    initial = HipRtcFgmresV2KernelIdentity(
        schema_version=HIP_RTC_FGMRES_V2_IDENTITY_SCHEMA_VERSION,
        abi_version=HIP_RTC_FGMRES_V2_ABI_VERSION,
        recurrence_abi_version=HIP_FGMRES_RECURRENCE_ABI_VERSION_V2,
        control_abi_version=HIP_FGMRES_CONTROL_ABI_VERSION_V2,
        kernel_name=HIP_RTC_FGMRES_V2_KERNEL_NAME,
        kernel_symbols=tuple(symbol for _, symbol in _SYMBOL_ITEMS),
        control_block_size=HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE,
        vector_block_size=HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE,
        reduction_values_per_block=(HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK),
        control_state_abi_hash=canonical_hash(_control_abi()),
        solve_record_abi_hash=canonical_hash(_record_abi()),
        kernel_interface_hash=canonical_hash(_kernel_abi()),
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
    identity: HipRtcFgmresV2KernelIdentity,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": identity.schema_version,
        "abi_version": identity.abi_version,
        "recurrence_abi_version": identity.recurrence_abi_version,
        "control_abi_version": identity.control_abi_version,
        "kernel_name": identity.kernel_name,
        "kernel_symbols": list(identity.kernel_symbols),
        "launch_geometry": {
            "control_block_size": identity.control_block_size,
            "vector_block_size": identity.vector_block_size,
            "reduction_values_per_block": identity.reduction_values_per_block,
        },
        "control_state_abi": {
            **_control_abi(),
            "abi_hash": identity.control_state_abi_hash,
        },
        "solve_record_abi": {
            **_record_abi(),
            "abi_hash": identity.solve_record_abi_hash,
        },
        "kernel_interface": {
            **_kernel_abi(),
            "interface_hash": identity.kernel_interface_hash,
        },
        "implemented_slice": {
            "control_modes": [
                "INIT",
                "BIND_RHS",
                "INITIAL_GATE",
                "RESTART_BEGIN",
                "PRECONDITION_ACCEPT",
                "OPERATOR_ACCEPT",
                "DOT_ACCEPT",
                "DGKS_DECIDE",
                "ARNOLDI_GIVENS",
                "BACKSUBSTITUTE",
                "VECTOR_ACCEPT",
                "CHECKPOINT_DECIDE",
                "CHECKPOINT_FINALIZE",
                "FINAL_GUARD",
            ],
            "vector_modes": [
                "COPY_INITIAL_X",
                "FORM_INITIAL_RESIDUAL",
                "NORMALIZE_V0",
                "APPLY_JACOBI_INDEXED",
                "MGS_SUBTRACT_INDEXED",
                "NORMALIZE_V_NEXT",
                "BUILD_TRIAL_X",
                "FORM_CANDIDATE_RESIDUAL",
                "COMMIT_CHECKPOINT",
                "PREFLIGHT_COMMIT_SOURCE",
            ],
            "spmv_modes": ["INITIAL", "ARNOLDI", "CANDIDATE"],
            "reduction_modes": [
                "LASSQ_LOAD",
                "LASSQ_TRUE_RESIDUAL",
                "LASSQ_WORK_W",
                "LASSQ_V_M",
                "LASSQ_WORK_W_MINUS_X",
                "LASSQ_SOLUTION_X",
                "DOT_W_VI",
                "LINF_LOAD",
                "LINF_TRUE_RESIDUAL",
                "LINF_V_M",
                "COMBINE_SUM",
                "COMBINE_LASSQ",
                "COMBINE_MAX",
            ],
            "reduction_targets": [
                "NONE",
                "DOT",
                "RHS_L2",
                "RHS_LINF",
                "INITIAL_L2",
                "INITIAL_LINF",
                "WORK_BEFORE",
                "AFTER_FIRST",
                "H_NEXT",
                "CANDIDATE_L2",
                "CANDIDATE_LINF",
                "UPDATE_L2",
                "COMMITTED_X_L2",
                "TRIAL_X_L2",
            ],
            "initial_dual_gate": True,
            "initial_final_guard": False,
            "fixed_global_raw_launch_validation": True,
            "fixed_global_final_guard_raw_launch": True,
            "first_column_partial_schedule_hash": canonical_hash(
                hip_fgmres_first_column_partial_schedule_payload_v2()
            ),
            "first_column_completion_schedule_hash": canonical_hash(
                _validated_completion_schedule(
                    _kernel_abi(),
                    code="hip_rtc_fgmres_v2_identity_invalid",
                )
            ),
            "first_column_candidate_preparation_schedule_hash": canonical_hash(
                _validated_candidate_preparation_schedule(
                    _kernel_abi(),
                    code="hip_rtc_fgmres_v2_identity_invalid",
                )
            ),
            "first_column_candidate_residual_schedule_hash": canonical_hash(
                _validated_candidate_residual_schedule(
                    _kernel_abi(),
                    code="hip_rtc_fgmres_v2_identity_invalid",
                )
            ),
            "first_column_candidate_scale_metrics_schedule_hash": canonical_hash(
                _validated_candidate_scale_metrics_schedule(
                    _kernel_abi(),
                    code="hip_rtc_fgmres_v2_identity_invalid",
                )
            ),
            "first_column_checkpoint_transaction_schedule_hash": canonical_hash(
                _validated_checkpoint_transaction_schedule(
                    _kernel_abi(),
                    code="hip_rtc_fgmres_v2_identity_invalid",
                )
            ),
            "first_arnoldi_column_partial": True,
            "first_arnoldi_column_complete": True,
            "first_pass_mgs_row0": True,
            "device_dgks_decision": True,
            "dgks_second_pass": True,
            "h_next_reduction": True,
            "v_next_normalization": True,
            "full_arnoldi_column": True,
            "first_column_candidate_state_published": True,
            "candidate_preparation_implemented": True,
            "candidate_preparation": True,
            "candidate_backsubstitute_implemented": True,
            "candidate_trial_vector_build_implemented": True,
            "candidate_solution_update_l2_implemented": True,
            "candidate_vector_accept_implemented": True,
            "candidate_envelope_implemented": False,
            "candidate_spmv_implemented": True,
            "candidate_spmv": True,
            "candidate_true_residual_implemented": True,
            "candidate_true_residual": True,
            "candidate_residual_l2_implemented": True,
            "candidate_residual_linf_implemented": True,
            "candidate_residual_metrics_implemented": True,
            "candidate_residual_metrics": True,
            "trial_and_committed_norms_implemented": True,
            "candidate_scale_metrics_implemented": True,
            "candidate_scale_metrics": True,
            "device_scale_metrics_priority_predicate_implemented": True,
            "checkpoint_transaction_planner_implemented": True,
            "checkpoint_transaction_raw_launch_owner_implemented": True,
            "checkpoint_transaction_rtc_owner_implemented": False,
            "checkpoint_transaction_kernel_numerical_implemented": True,
            "checkpoint_transaction_valid_predecessor_path_implemented": True,
            "checkpoint_transaction_authoritative_owner_implemented": False,
            "checkpoint_commit_source_preflight_implemented": True,
            "checkpoint_transaction_invalid_source_all_or_nothing_proven": True,
            "checkpoint_transaction_invalid_source_all_or_nothing_scope": (
                "fixed_same_stream_four_launch_transaction_under_exclusive_"
                "source_and_destination_ownership"
            ),
            "checkpoint_transaction_range_overlap_validation_implemented": False,
            "checkpoint_transaction_atomic_host_enqueue_implemented": False,
            "checkpoint_transaction_xscale_failure_oracle_state_parity": False,
            "checkpoint_decide_implemented": True,
            "checkpoint_decide": True,
            "checkpoint_commit_implemented": True,
            "checkpoint_finalize_implemented": True,
            "single_pending_stream_enforced": True,
            "epoch_semantics": ("admission_order_only_not_global_numeric_success"),
            "arnoldi": True,
            "arnoldi_scope": "restart_one_column_zero_through_givens",
            "dgks": True,
            "dgks_scope": "restart_one_column_zero_conditional_second_pass",
            "givens": True,
            "backsolve": True,
            "checkpoint_commit": True,
            "full_recurrence_implemented": False,
            "full_solver": False,
            "live_solver_ready": False,
            "iteration_host_copy_zero_proven": False,
            "native_numerical_parity": False,
            "native_numerical_parity_scope": (
                "requires_downstream_model_case_parity_receipt"
            ),
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
    if type(identity) is not HipRtcFgmresV2KernelIdentity:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_invalid",
            "FGMRES v2 identity type is invalid.",
        )
    integer_fields = (
        identity.abi_version,
        identity.recurrence_abi_version,
        identity.control_abi_version,
        identity.control_block_size,
        identity.vector_block_size,
        identity.reduction_values_per_block,
        identity.hiprtc_version_major,
        identity.hiprtc_version_minor,
        identity.code_object_byte_length,
    )
    string_fields = (
        identity.schema_version,
        identity.kernel_name,
        identity.control_state_abi_hash,
        identity.solve_record_abi_hash,
        identity.kernel_interface_hash,
        identity.source_resource,
        identity.source_sha256,
        identity.architecture,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if (
        any(type(value) is not int for value in integer_fields)
        or any(type(value) is not str for value in string_fields)
        or type(identity.kernel_symbols) is not tuple
        or any(type(value) is not str for value in identity.kernel_symbols)
        or type(identity.compile_options) is not tuple
        or any(type(value) is not str for value in identity.compile_options)
        or type(identity._code_object_witness) is not bytes
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_invalid",
            "FGMRES v2 identity tuple, scalar, or witness fields are invalid.",
        )
    expected_symbols = tuple(symbol for _, symbol in _SYMBOL_ITEMS)
    if (
        identity.schema_version != HIP_RTC_FGMRES_V2_IDENTITY_SCHEMA_VERSION
        or identity.abi_version != HIP_RTC_FGMRES_V2_ABI_VERSION
        or identity.recurrence_abi_version != HIP_FGMRES_RECURRENCE_ABI_VERSION_V2
        or identity.control_abi_version != HIP_FGMRES_CONTROL_ABI_VERSION_V2
        or identity.kernel_name != HIP_RTC_FGMRES_V2_KERNEL_NAME
        or identity.kernel_symbols != expected_symbols
        or identity.control_block_size != HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE
        or identity.vector_block_size != HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE
        or identity.reduction_values_per_block
        != HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK
        or identity.control_state_abi_hash != canonical_hash(_control_abi())
        or identity.solve_record_abi_hash != canonical_hash(_record_abi())
        or identity.kernel_interface_hash != canonical_hash(_kernel_abi())
        or identity.source_resource != _SOURCE_RESOURCE
        or identity.source_sha256 != _sha256_bytes(_fixed_source())
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_invalid",
            "Fixed FGMRES recurrence-v2 ABI is invalid.",
        )
    try:
        _validate_architecture(identity.architecture)
        _validate_rtc_library_identity(identity.hiprtc_library)
        _validate_runtime_identity(identity.runtime_library)
    except HipRtcError as exc:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_invalid",
            exc.message,
        ) from exc
    if identity.compile_options != (
        f"--offload-arch={identity.architecture}",
        *_FIXED_OPTION_SUFFIX,
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_invalid",
            "FGMRES v2 compile options are not fixed.",
        )
    hashes = (
        identity.control_state_abi_hash,
        identity.solve_record_abi_hash,
        identity.kernel_interface_hash,
        identity.source_sha256,
        identity.hiprtc_library.sha256,
        identity.runtime_library.sha256,
        identity.code_object_sha256,
        identity.identity_hash,
    )
    if any(not _valid_sha256(value) for value in hashes):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_invalid",
            "FGMRES v2 identity hash is invalid.",
        )
    if (
        len(identity._code_object_witness) != identity.code_object_byte_length
        or _sha256_bytes(identity._code_object_witness) != identity.code_object_sha256
        or identity.code_object_byte_length <= 0
        or identity.hiprtc_version_major < 0
        or identity.hiprtc_version_minor < 0
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_invalid",
            "FGMRES v2 code-object witness or version is invalid.",
        )
    if identity.identity_hash != canonical_hash(
        _identity_payload(identity, include_hash=False)
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_identity_hash_mismatch",
            "FGMRES v2 identity hash is invalid.",
        )


def _fixed_source() -> bytes:
    try:
        source = _SOURCE_PATH.read_bytes()
    except OSError as exc:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_source_missing",
            f"The package-owned FGMRES v2 source is unavailable: {type(exc).__name__}.",
        ) from exc
    interface = _kernel_abi()
    try:
        _validated_predecessor_validation_schedule(
            interface,
            code="hip_rtc_fgmres_v2_source_invalid",
        )
        _validated_checkpoint_transaction_schedule(
            interface,
            code="hip_rtc_fgmres_v2_source_invalid",
        )
    except HipRtcFgmresV2Error as exc:
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_source_invalid",
            "Package-owned FGMRES v2 source is not bound to the canonical "
            "column-zero checkpoint-transaction schedule.",
        ) from exc
    expected_symbols = tuple(symbol for _, symbol in _SYMBOL_ITEMS)
    declared_symbols = tuple(
        match.decode("ascii")
        for match in re.findall(
            rb'extern\s+"C"\s+__global__\s+void\s+([A-Za-z0-9_]+)\s*\(',
            source,
        )
    )
    signatures_valid = declared_symbols == expected_symbols
    canonical_signatures = interface["signatures"]
    for symbol in expected_symbols:
        expected = _canonical_source_arguments(canonical_signatures[symbol])
        pattern = re.compile(
            rb'extern\s+"C"\s+__global__\s+void\s+'
            + re.escape(symbol.encode("ascii"))
            + rb"\s*\((.*?)\)\s*\{",
            re.DOTALL,
        )
        matches = pattern.findall(source)
        normalized = b"".join(matches[0].split()) if len(matches) == 1 else b""
        if len(matches) != 1 or normalized != expected:
            signatures_valid = False
            break
    interface_marker = (
        "// engine-v2-fgmres-recurrence-interface-v2: " + canonical_hash(interface)
    ).encode("ascii")
    constant_markers = tuple(
        f"constexpr int {name} = {value};".encode("ascii")
        for name, value in _source_abi_constant_bindings()
    )
    if (
        not source
        or not signatures_valid
        or source.count(interface_marker) != 1
        or any(source.count(marker) != 1 for marker in constant_markers)
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_source_invalid",
            "Package-owned FGMRES v2 source must expose exactly four fixed "
            "symbols and bind every canonical interface constant.",
        )
    return source


def _canonical_source_arguments(signature: str) -> bytes:
    if (
        type(signature) is not str
        or not signature.startswith("void(")
        or not signature.endswith(")")
    ):
        raise HipRtcFgmresV2Error(
            "hip_rtc_fgmres_v2_source_invalid",
            "Canonical FGMRES v2 signature is malformed.",
        )
    return b"".join(signature[5:-1].encode("ascii").split())


def _camel(name: str) -> str:
    return "".join(part[:1].upper() + part[1:].lower() for part in name.split("_"))


def _source_abi_constant_bindings() -> tuple[tuple[str, int], ...]:
    control = _control_abi()
    record = _record_abi()
    interface = _kernel_abi()
    control_offsets = {
        row["name"]: int(row["offset_bytes"]) for row in control["fields"]
    }
    header_offsets = {
        row["name"]: int(row["offset_bytes"]) for row in record["header_fields"]
    }
    restart_offsets = {
        row["name"]: int(row["offset_bytes"]) for row in record["restart_fields"]
    }
    bindings: list[tuple[str, int]] = [
        ("kControlAbiVersion", int(control["control_abi_version"])),
        ("kRecurrenceAbiVersion", int(record["recurrence_abi_version"])),
        ("kControlBytes", int(control["byte_length"])),
        ("kHeaderBytes", int(record["header_bytes"])),
        ("kRestartBytes", int(record["restart_bytes"])),
        ("kMaximumRestartDimension", HIP_FGMRES_MAX_RESTART_DIMENSION),
        ("kMaximumIterations", HIP_FGMRES_MAX_ITERATIONS),
        ("kControlBlockSize", HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE),
        ("kVectorBlockSize", HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE),
        (
            "kReductionValuesPerBlock",
            HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK,
        ),
    ]
    bindings.extend(
        (f"kControlOffset{_camel(name)}", offset)
        for name, offset in control_offsets.items()
    )
    for category, prefix in (
        ("phase_codes", "kPhase"),
        ("control_mode_codes", "kControlMode"),
        ("vector_mode_codes", "kVectorMode"),
        ("vector_gate_codes", "kVectorGate"),
        ("spmv_mode_codes", "kSpmvMode"),
        ("reduction_mode_codes", "kReductionMode"),
        ("reduction_target_codes", "kReductionTarget"),
        ("failure_origin_codes", "kFailureOrigin"),
        ("predecessor_validation_state_codes", "kPredecessorValidation"),
    ):
        bindings.extend(
            (f"{prefix}{_camel(name)}", int(value))
            for name, value in control[category].items()
        )
    bindings.extend(
        (f"kCandidateReasonBit{_camel(name)}", int(value))
        for name, value in control["candidate_reason_bits"].items()
    )
    bindings.extend(
        (f"kReductionValidBit{_camel(name)}", int(value))
        for name, value in control["reduction_valid_bits"].items()
    )
    bindings.extend(
        (
            f"kReductionTargetOffset{_camel(name)}",
            int(description["offset_bytes"]),
        )
        for name, description in control["reduction_target_fields"].items()
    )
    bindings.extend(
        (f"kError{_camel(name)}", int(value))
        for name, value in interface["device_error_masks"].items()
    )
    bindings.extend(
        (f"kRecordOffset{_camel(name)}", offset)
        for name, offset in header_offsets.items()
    )
    bindings.extend(
        (f"kRestartOffset{_camel(name)}", offset)
        for name, offset in restart_offsets.items()
    )
    for category, prefix in (
        ("terminal_status_codes", "kTerminal"),
        ("termination_codes", "kTermination"),
        ("restart_hint_codes", "kRestartHint"),
    ):
        bindings.extend(
            (f"{prefix}{_camel(name)}", int(value))
            for name, value in record[category].items()
        )
    bindings.extend(
        (f"kRestartFlagBit{_camel(name)}", int(value))
        for name, value in record["restart_flag_bits"].items()
    )
    return tuple(bindings)


def _validate_reduction_mode_target(
    mode: int,
    target: int,
    value_count: int,
) -> None:
    final_stage = reduction_output_count_v2(value_count) == 1
    if not final_stage:
        if target != _REDUCTION_TARGETS["NONE"]:
            raise _launch_contract_error(
                "a nonfinal reduction stage must use target NONE."
            )
        return
    if target == _REDUCTION_TARGETS["NONE"]:
        raise _launch_contract_error(
            "a final reduction stage must publish a named target."
        )
    expected: frozenset[int]
    if mode == _REDUCTION_MODES["LASSQ_LOAD"]:
        expected = frozenset({_REDUCTION_TARGETS["RHS_L2"]})
    elif mode == _REDUCTION_MODES["LASSQ_TRUE_RESIDUAL"]:
        expected = frozenset({_REDUCTION_TARGETS["INITIAL_L2"]})
    elif mode == _REDUCTION_MODES["LINF_LOAD"]:
        expected = frozenset({_REDUCTION_TARGETS["RHS_LINF"]})
    elif mode == _REDUCTION_MODES["LINF_TRUE_RESIDUAL"]:
        expected = frozenset({_REDUCTION_TARGETS["INITIAL_LINF"]})
    elif mode == _REDUCTION_MODES["LASSQ_WORK_W"]:
        expected = frozenset(
            {
                _REDUCTION_TARGETS["WORK_BEFORE"],
                _REDUCTION_TARGETS["AFTER_FIRST"],
                _REDUCTION_TARGETS["H_NEXT"],
                _REDUCTION_TARGETS["TRIAL_X_L2"],
            }
        )
    elif mode == _REDUCTION_MODES["LASSQ_V_M"]:
        expected = frozenset({_REDUCTION_TARGETS["CANDIDATE_L2"]})
    elif mode == _REDUCTION_MODES["LASSQ_WORK_W_MINUS_X"]:
        expected = frozenset({_REDUCTION_TARGETS["UPDATE_L2"]})
    elif mode == _REDUCTION_MODES["LASSQ_SOLUTION_X"]:
        expected = frozenset({_REDUCTION_TARGETS["COMMITTED_X_L2"]})
    elif mode == _REDUCTION_MODES["LINF_V_M"]:
        expected = frozenset({_REDUCTION_TARGETS["CANDIDATE_LINF"]})
    elif mode == _REDUCTION_MODES["DOT_W_VI"]:
        expected = _DOT_TARGETS
    elif mode == _REDUCTION_MODES["COMBINE_SUM"]:
        expected = _DOT_TARGETS
    elif mode == _REDUCTION_MODES["COMBINE_LASSQ"]:
        expected = _L2_TARGETS
    elif mode == _REDUCTION_MODES["COMBINE_MAX"]:
        expected = _LINF_TARGETS
    else:  # pragma: no cover - guarded by the implemented mode allowlist
        raise _launch_contract_error("reduction_mode is not implemented.")
    if target not in expected:
        raise _launch_contract_error(
            "reduction_target is incompatible with the implemented reduction_mode."
        )


def _validate_vector_pointer_aliases(
    mode: int,
    pointers: tuple[int, ...],
) -> None:
    if mode == _VECTOR_MODES["FORM_CANDIDATE_RESIDUAL"]:
        active_bases = (
            pointers[1],  # reduced_load_base
            pointers[6],  # basis_v_base, admitted in-place V[M] input/output
            pointers[9],  # control_state_base
            pointers[10],  # solve_record_base
        )
        message = (
            "candidate residual admits only the exact in-place V[M] update; "
            "load, basis, control, and solve-record bases must remain distinct."
        )
    elif mode in (
        _VECTOR_MODES["COMMIT_CHECKPOINT"],
        _VECTOR_MODES["PREFLIGHT_COMMIT_SOURCE"],
    ):
        forbidden_pairs = (
            (5, 3),  # work_w_base -> solution_x_base
            (6, 4),  # basis_v_base -> true_residual_base
            (5, 4),  # work_w_base -> true_residual_base
            (6, 3),  # basis_v_base -> solution_x_base
            (3, 4),  # committed destinations
        )
        if any(pointers[left] == pointers[right] for left, right in forbidden_pairs):
            raise _launch_contract_error(
                "checkpoint preflight/commit source/destination allocation bases "
                "violate the canonical forbidden exact-alias pairs."
            )
        if any(
            pointers[destination] in (pointers[9], pointers[10])
            for destination in (3, 4)
        ):
            raise _launch_contract_error(
                "checkpoint preflight/commit destinations must not alias control "
                "or solve-record allocation bases."
            )
        return
    else:
        return
    if len(set(active_bases)) != len(active_bases):
        raise _launch_contract_error(message)


def _validate_spmv_pointer_aliases(
    mode: int,
    pointers: tuple[int, ...],
) -> None:
    if mode != _SPMV_MODES["CANDIDATE"]:
        return
    active_bases = (
        pointers[0],  # row_ptr_base
        pointers[1],  # column_indices_base
        pointers[2],  # values_base
        pointers[4],  # work_w_base, candidate trial input
        pointers[5],  # basis_v_base, V[M] output
        pointers[7],  # control_state_base
        pointers[8],  # solve_record_base
    )
    if len(set(active_bases)) != len(active_bases):
        raise _launch_contract_error(
            "candidate SpMV requires distinct allocation bases for CSR, trial "
            "input, V[M] output, control, and solve record."
        )


def _validate_reduction_pointer_aliases(
    mode: int,
    pointers: tuple[int, ...],
) -> None:
    output = pointers[6]
    source_indices: tuple[int, ...]
    if mode in (
        _REDUCTION_MODES["LASSQ_LOAD"],
        _REDUCTION_MODES["LINF_LOAD"],
    ):
        source_indices = (0,)
    elif mode in (
        _REDUCTION_MODES["LASSQ_TRUE_RESIDUAL"],
        _REDUCTION_MODES["LINF_TRUE_RESIDUAL"],
    ):
        source_indices = (2,)
    elif mode == _REDUCTION_MODES["LASSQ_WORK_W"]:
        source_indices = (3,)
    elif mode == _REDUCTION_MODES["LASSQ_WORK_W_MINUS_X"]:
        source_indices = (1, 3)
    elif mode == _REDUCTION_MODES["LASSQ_SOLUTION_X"]:
        source_indices = (1,)
    elif mode in (
        _REDUCTION_MODES["LASSQ_V_M"],
        _REDUCTION_MODES["LINF_V_M"],
    ):
        source_indices = (4,)
    elif mode == _REDUCTION_MODES["DOT_W_VI"]:
        source_indices = (3, 4)
    else:
        source_indices = (5,)
    if output in (pointers[7], pointers[8]):
        raise _launch_contract_error(
            "reduction output base must not alias control or solve-record base."
        )
    if any(output == pointers[index] for index in source_indices):
        raise _launch_contract_error(
            "reduction output base must differ from every active stage source base."
        )


def _validate_control_launch(
    mode: int,
    schedule_epoch: int,
    expected_restart: int,
    expected_column: int,
    row_index: int,
    pass_index: int,
    free_dof_count: int,
    restart_dimension: int,
    max_iterations: int,
) -> None:
    stages = len(reduction_stage_output_counts_v2(free_dof_count))
    boundary = _global_initial_schedule_boundary(stages)
    initial_variants: dict[int, tuple[tuple[int, int, int, int, int], ...]] = {
        _CONTROL_MODES["INIT"]: ((0, -1, -1, -1, -1),),
        _CONTROL_MODES["BIND_RHS"]: ((2 + 2 * stages, -1, -1, -1, -1),),
        _CONTROL_MODES["INITIAL_GATE"]: ((6 + 4 * stages, -1, -1, -1, -1),),
        _CONTROL_MODES["OPERATOR_ACCEPT"]: ((4 + 2 * stages, -1, -1, -1, -1),),
    }
    actual = (
        schedule_epoch,
        expected_restart,
        expected_column,
        row_index,
        pass_index,
    )
    if actual in initial_variants.get(mode, ()):
        return

    maximum_restart_count = (
        0
        if max_iterations == 0
        else (max_iterations + restart_dimension - 1) // restart_dimension
    )
    restart_base = _global_restart_schedule_base(
        boundary,
        stages,
        restart_dimension,
        expected_restart,
    )
    if mode == _CONTROL_MODES["RESTART_BEGIN"]:
        valid = 1 <= expected_restart <= maximum_restart_count and actual == (
            restart_base,
            expected_restart,
            -1,
            -1,
            -1,
        )
    elif mode == _CONTROL_MODES["FINAL_GUARD"]:
        final_epoch = (
            boundary
            + maximum_restart_count
            * _global_restart_schedule_stride(
                stages,
                restart_dimension,
            )
        )
        valid = max_iterations > 0 and actual == (
            final_epoch,
            maximum_restart_count,
            restart_dimension - 1,
            -1,
            -1,
        )
    elif not (
        1 <= expected_restart <= maximum_restart_count
        and 0 <= expected_column < restart_dimension
    ):
        valid = False
    else:
        column = expected_column
        column_base = _global_column_schedule_base(
            boundary,
            stages,
            restart_dimension,
            expected_restart,
            column,
        )
        (
            first_pass_base,
            after_first_base,
            second_pass_base,
            h_next_base,
            update_base,
            _metrics_base,
            checkpoint_base,
        ) = _global_column_local_bases(column_base, stages, column)
        fixed_variants: dict[int, tuple[int, int]] = {
            _CONTROL_MODES["PRECONDITION_ACCEPT"]: (column_base + 1, -1),
            _CONTROL_MODES["DGKS_DECIDE"]: (after_first_base + stages, 0),
            _CONTROL_MODES["ARNOLDI_GIVENS"]: (h_next_base + stages + 1, -1),
            _CONTROL_MODES["BACKSUBSTITUTE"]: (h_next_base + stages + 2, -1),
            _CONTROL_MODES["VECTOR_ACCEPT"]: (update_base + stages, -1),
            _CONTROL_MODES["CHECKPOINT_DECIDE"]: (checkpoint_base, -1),
            _CONTROL_MODES["CHECKPOINT_FINALIZE"]: (checkpoint_base + 2, -1),
            _CONTROL_MODES["PREDECESSOR_VALIDATE"]: (checkpoint_base, -1),
        }
        if mode == _CONTROL_MODES["OPERATOR_ACCEPT"]:
            valid = row_index == pass_index == -1 and schedule_epoch in (
                column_base + 3,
                update_base + stages + 2,
            )
        elif mode == _CONTROL_MODES["DOT_ACCEPT"]:
            valid = 0 <= row_index <= column and (
                (
                    pass_index == 0
                    and schedule_epoch
                    == first_pass_base + row_index * (stages + 2) + stages
                )
                or (
                    pass_index == 1
                    and schedule_epoch
                    == second_pass_base + row_index * (stages + 2) + stages
                )
            )
        elif mode in fixed_variants:
            required_epoch, required_pass = fixed_variants[mode]
            valid = (
                schedule_epoch == required_epoch
                and row_index == -1
                and pass_index == required_pass
            )
        else:
            valid = False
    if not valid:
        raise _launch_contract_error(
            "control coordinates do not match the canonical fixed global schedule."
        )


def _validate_vector_launch(
    mode: int,
    gate: int,
    schedule_epoch: int,
    expected_restart: int,
    expected_column: int,
    logical_index: int,
    free_dof_count: int,
) -> None:
    stages = len(reduction_stage_output_counts_v2(free_dof_count))
    boundary = _global_initial_schedule_boundary(stages)
    initial_variants = {
        _VECTOR_MODES["COPY_INITIAL_X"]: ((_VECTOR_GATES["ACTIVE"], 1, -1, -1, 0),),
        _VECTOR_MODES["FORM_INITIAL_RESIDUAL"]: (
            (_VECTOR_GATES["ACTIVE"], 5 + 2 * stages, -1, -1, 0),
        ),
    }
    actual = (
        gate,
        schedule_epoch,
        expected_restart,
        expected_column,
        logical_index,
    )
    if actual in initial_variants.get(mode, ()):
        return
    valid = False
    if expected_restart >= 1 and expected_column >= 0:
        for restart_dimension in range(1, HIP_FGMRES_MAX_RESTART_DIMENSION + 1):
            if expected_column >= restart_dimension:
                continue
            restart_base = _global_restart_schedule_base(
                boundary,
                stages,
                restart_dimension,
                expected_restart,
            )
            column_base = _global_column_schedule_base(
                boundary,
                stages,
                restart_dimension,
                expected_restart,
                expected_column,
            )
            (
                first_pass_base,
                _after_first_base,
                second_pass_base,
                h_next_base,
                update_base,
                _metrics_base,
                checkpoint_base,
            ) = _global_column_local_bases(
                column_base,
                stages,
                expected_column,
            )
            if mode == _VECTOR_MODES["NORMALIZE_V0"]:
                candidate = (
                    _VECTOR_GATES["ACTIVE"],
                    restart_base + 1,
                    expected_restart,
                    0,
                    0,
                )
                valid = actual == candidate
            elif mode == _VECTOR_MODES["APPLY_JACOBI_INDEXED"]:
                valid = actual == (
                    _VECTOR_GATES["ACTIVE"],
                    column_base,
                    expected_restart,
                    expected_column,
                    expected_column,
                )
            elif mode == _VECTOR_MODES["MGS_SUBTRACT_INDEXED"]:
                valid = 0 <= logical_index <= expected_column and (
                    (
                        gate == _VECTOR_GATES["ACTIVE"]
                        and schedule_epoch
                        == first_pass_base + logical_index * (stages + 2) + stages + 1
                    )
                    or (
                        gate == _VECTOR_GATES["DGKS_SECOND_PASS"]
                        and schedule_epoch
                        == second_pass_base + logical_index * (stages + 2) + stages + 1
                    )
                )
            elif mode == _VECTOR_MODES["NORMALIZE_V_NEXT"]:
                valid = actual == (
                    _VECTOR_GATES["ACTIVE"],
                    h_next_base + stages,
                    expected_restart,
                    expected_column,
                    expected_column + 1,
                )
            elif mode == _VECTOR_MODES["BUILD_TRIAL_X"]:
                valid = actual == (
                    _VECTOR_GATES["CANDIDATE_REQUIRED"],
                    update_base - 1,
                    expected_restart,
                    expected_column,
                    expected_column,
                )
            elif mode == _VECTOR_MODES["FORM_CANDIDATE_RESIDUAL"]:
                valid = actual == (
                    _VECTOR_GATES["CANDIDATE_REQUIRED"],
                    update_base + stages + 3,
                    expected_restart,
                    expected_column,
                    restart_dimension,
                )
            elif mode in (
                _VECTOR_MODES["COMMIT_CHECKPOINT"],
                _VECTOR_MODES["PREFLIGHT_COMMIT_SOURCE"],
            ):
                valid = actual == (
                    _VECTOR_GATES["COMMIT_REQUIRED"],
                    checkpoint_base + 1,
                    expected_restart,
                    expected_column,
                    restart_dimension,
                )
            if valid:
                break
    if not valid:
        raise _launch_contract_error(
            "vector coordinates do not match the canonical fixed global schedule."
        )


def _validate_spmv_launch(
    mode: int,
    schedule_epoch: int,
    expected_restart: int,
    expected_column: int,
    logical_index: int,
    free_dof_count: int,
) -> None:
    stages = len(reduction_stage_output_counts_v2(free_dof_count))
    actual = (
        schedule_epoch,
        expected_restart,
        expected_column,
        logical_index,
    )
    if mode == _SPMV_MODES["INITIAL"] and actual == (
        3 + 2 * stages,
        -1,
        -1,
        0,
    ):
        return
    valid = False
    if expected_restart >= 1 and expected_column >= 0:
        boundary = _global_initial_schedule_boundary(stages)
        for restart_dimension in range(1, HIP_FGMRES_MAX_RESTART_DIMENSION + 1):
            if expected_column >= restart_dimension:
                continue
            column_base = _global_column_schedule_base(
                boundary,
                stages,
                restart_dimension,
                expected_restart,
                expected_column,
            )
            *_, update_base, _metrics_base, _checkpoint_base = (
                _global_column_local_bases(
                    column_base,
                    stages,
                    expected_column,
                )
            )
            if mode == _SPMV_MODES["ARNOLDI"]:
                valid = actual == (
                    column_base + 2,
                    expected_restart,
                    expected_column,
                    expected_column,
                )
            elif mode == _SPMV_MODES["CANDIDATE"]:
                valid = actual == (
                    update_base + stages + 1,
                    expected_restart,
                    expected_column,
                    restart_dimension,
                )
            if valid:
                break
    if not valid:
        raise _launch_contract_error(
            "SpMV coordinates do not match the canonical fixed global schedule."
        )


def _validate_reduction_coordinates(
    mode: int,
    target: int,
    schedule_epoch: int,
    expected_restart: int,
    expected_column: int,
    reduction_epoch: int,
    value_count: int,
    logical_index: int,
) -> None:
    remaining_stage_count = len(reduction_stage_output_counts_v2(value_count))
    maximum_stage_count = len(reduction_stage_output_counts_v2(_INT32_MAX))
    for stages in range(1, maximum_stage_count + 1):
        if (expected_restart, expected_column, logical_index) == (-1, -1, 0):
            initial_specs = (
                (
                    2,
                    0,
                    _REDUCTION_MODES["LASSQ_LOAD"],
                    _REDUCTION_MODES["COMBINE_LASSQ"],
                    _REDUCTION_TARGETS["RHS_L2"],
                ),
                (
                    2 + stages,
                    stages,
                    _REDUCTION_MODES["LINF_LOAD"],
                    _REDUCTION_MODES["COMBINE_MAX"],
                    _REDUCTION_TARGETS["RHS_LINF"],
                ),
                (
                    6 + 2 * stages,
                    2 * stages,
                    _REDUCTION_MODES["LASSQ_TRUE_RESIDUAL"],
                    _REDUCTION_MODES["COMBINE_LASSQ"],
                    _REDUCTION_TARGETS["INITIAL_L2"],
                ),
                (
                    6 + 3 * stages,
                    3 * stages,
                    _REDUCTION_MODES["LINF_TRUE_RESIDUAL"],
                    _REDUCTION_MODES["COMBINE_MAX"],
                    _REDUCTION_TARGETS["INITIAL_LINF"],
                ),
            )
            if any(
                _reduction_tree_coordinates_match(
                    mode,
                    target,
                    schedule_epoch,
                    reduction_epoch,
                    remaining_stage_count,
                    stages,
                    *spec,
                )
                for spec in initial_specs
            ):
                return

        if expected_restart < 1 or expected_column < 0:
            continue
        boundary = _global_initial_schedule_boundary(stages)
        column = expected_column
        for restart_dimension in range(1, HIP_FGMRES_MAX_RESTART_DIMENSION + 1):
            if column >= restart_dimension:
                continue
            column_base = _global_column_schedule_base(
                boundary,
                stages,
                restart_dimension,
                expected_restart,
                column,
            )
            column_reduction_base = _global_column_reduction_base(
                stages,
                restart_dimension,
                expected_restart,
                column,
            )
            (
                first_pass_base,
                after_first_base,
                second_pass_base,
                h_next_base,
                update_base,
                metrics_base,
                _checkpoint_base,
            ) = _global_column_local_bases(column_base, stages, column)
            specs: list[tuple[int, int, int, int, int, int]] = [
                (
                    column,
                    column_base + 4,
                    column_reduction_base,
                    _REDUCTION_MODES["LASSQ_WORK_W"],
                    _REDUCTION_MODES["COMBINE_LASSQ"],
                    _REDUCTION_TARGETS["WORK_BEFORE"],
                )
            ]
            specs.extend(
                (
                    row,
                    first_pass_base + row * (stages + 2),
                    column_reduction_base + (1 + row) * stages,
                    _REDUCTION_MODES["DOT_W_VI"],
                    _REDUCTION_MODES["COMBINE_SUM"],
                    _REDUCTION_TARGETS["DOT"],
                )
                for row in range(column + 1)
            )
            specs.append(
                (
                    column,
                    after_first_base,
                    column_reduction_base + (column + 2) * stages,
                    _REDUCTION_MODES["LASSQ_WORK_W"],
                    _REDUCTION_MODES["COMBINE_LASSQ"],
                    _REDUCTION_TARGETS["AFTER_FIRST"],
                )
            )
            specs.extend(
                (
                    row,
                    second_pass_base + row * (stages + 2),
                    column_reduction_base + (column + 3 + row) * stages,
                    _REDUCTION_MODES["DOT_W_VI"],
                    _REDUCTION_MODES["COMBINE_SUM"],
                    _REDUCTION_TARGETS["DOT"],
                )
                for row in range(column + 1)
            )
            specs.extend(
                (
                    (
                        column,
                        h_next_base,
                        column_reduction_base + (2 * column + 4) * stages,
                        _REDUCTION_MODES["LASSQ_WORK_W"],
                        _REDUCTION_MODES["COMBINE_LASSQ"],
                        _REDUCTION_TARGETS["H_NEXT"],
                    ),
                    (
                        column,
                        update_base,
                        column_reduction_base + (2 * column + 5) * stages,
                        _REDUCTION_MODES["LASSQ_WORK_W_MINUS_X"],
                        _REDUCTION_MODES["COMBINE_LASSQ"],
                        _REDUCTION_TARGETS["UPDATE_L2"],
                    ),
                    (
                        restart_dimension,
                        metrics_base,
                        column_reduction_base + (2 * column + 6) * stages,
                        _REDUCTION_MODES["LASSQ_V_M"],
                        _REDUCTION_MODES["COMBINE_LASSQ"],
                        _REDUCTION_TARGETS["CANDIDATE_L2"],
                    ),
                    (
                        restart_dimension,
                        metrics_base + stages,
                        column_reduction_base + (2 * column + 7) * stages,
                        _REDUCTION_MODES["LINF_V_M"],
                        _REDUCTION_MODES["COMBINE_MAX"],
                        _REDUCTION_TARGETS["CANDIDATE_LINF"],
                    ),
                    (
                        column,
                        metrics_base + 2 * stages,
                        column_reduction_base + (2 * column + 8) * stages,
                        _REDUCTION_MODES["LASSQ_WORK_W"],
                        _REDUCTION_MODES["COMBINE_LASSQ"],
                        _REDUCTION_TARGETS["TRIAL_X_L2"],
                    ),
                    (
                        column,
                        metrics_base + 3 * stages,
                        column_reduction_base + (2 * column + 9) * stages,
                        _REDUCTION_MODES["LASSQ_SOLUTION_X"],
                        _REDUCTION_MODES["COMBINE_LASSQ"],
                        _REDUCTION_TARGETS["COMMITTED_X_L2"],
                    ),
                )
            )
            for (
                required_logical_index,
                tree_schedule_base,
                tree_reduction_base,
                first_mode,
                combine_mode,
                final_target,
            ) in specs:
                if logical_index != required_logical_index:
                    continue
                if _reduction_tree_coordinates_match(
                    mode,
                    target,
                    schedule_epoch,
                    reduction_epoch,
                    remaining_stage_count,
                    stages,
                    tree_schedule_base,
                    tree_reduction_base,
                    first_mode,
                    combine_mode,
                    final_target,
                ):
                    return
    raise _launch_contract_error(
        "reduction coordinates do not match the canonical fixed global schedule."
    )


def _reduction_tree_coordinates_match(
    mode: int,
    target: int,
    schedule_epoch: int,
    reduction_epoch: int,
    remaining_stage_count: int,
    total_stage_count: int,
    tree_schedule_base: int,
    tree_reduction_base: int,
    first_mode: int,
    combine_mode: int,
    final_target: int,
) -> bool:
    stage = reduction_epoch - tree_reduction_base
    if not 0 <= stage < total_stage_count:
        return False
    return (
        remaining_stage_count == total_stage_count - stage
        and schedule_epoch == tree_schedule_base + stage
        and mode == (first_mode if stage == 0 else combine_mode)
        and target
        == (
            final_target
            if stage + 1 == total_stage_count
            else _REDUCTION_TARGETS["NONE"]
        )
    )


def _global_initial_schedule_boundary(reduction_stage_count: int) -> int:
    """Return ``B``, the first restart's fixed schedule epoch."""

    return 7 + 4 * reduction_stage_count


def _global_column_schedule_stride(
    reduction_stage_count: int,
    column_index: int,
) -> int:
    """Return variable column stride ``L_j`` for one physical slot."""

    return 20 + 4 * column_index + (10 + 2 * column_index) * reduction_stage_count


def _global_restart_reduction_stride(
    reduction_stage_count: int,
    restart_dimension: int,
) -> int:
    """Return ``D``, one restart's fixed reduction-epoch stride."""

    return (
        restart_dimension * restart_dimension + 9 * restart_dimension
    ) * reduction_stage_count


def _global_restart_schedule_stride(
    reduction_stage_count: int,
    restart_dimension: int,
) -> int:
    """Return ``H``, restart preamble plus all ``M`` variable columns."""

    return (
        2
        + 2 * restart_dimension * restart_dimension
        + 18 * restart_dimension
        + _global_restart_reduction_stride(
            reduction_stage_count,
            restart_dimension,
        )
    )


def _global_restart_schedule_base(
    initial_boundary: int,
    reduction_stage_count: int,
    restart_dimension: int,
    restart_index: int,
) -> int:
    return initial_boundary + (restart_index - 1) * _global_restart_schedule_stride(
        reduction_stage_count,
        restart_dimension,
    )


def _global_column_schedule_base(
    initial_boundary: int,
    reduction_stage_count: int,
    restart_dimension: int,
    restart_index: int,
    column_index: int,
) -> int:
    """Return global schedule base ``E[r,j]`` for Jacobi launch ``j``."""

    return (
        _global_restart_schedule_base(
            initial_boundary,
            reduction_stage_count,
            restart_dimension,
            restart_index,
        )
        + 2
        + 2 * column_index * column_index
        + 18 * column_index
        + (column_index * column_index + 9 * column_index) * reduction_stage_count
    )


def _global_column_reduction_base(
    reduction_stage_count: int,
    restart_dimension: int,
    restart_index: int,
    column_index: int,
) -> int:
    """Return global reduction base ``Q[r,j]`` for work-before tree ``j``."""

    return (
        4 * reduction_stage_count
        + (restart_index - 1)
        * _global_restart_reduction_stride(
            reduction_stage_count,
            restart_dimension,
        )
        + (column_index * column_index + 9 * column_index) * reduction_stage_count
    )


def _global_column_local_bases(
    column_schedule_base: int,
    reduction_stage_count: int,
    column_index: int,
) -> tuple[int, int, int, int, int, int, int]:
    """Return exact local bases from first-pass dots through checkpoint."""

    first_pass_base = column_schedule_base + 4 + reduction_stage_count
    after_first_base = first_pass_base + (column_index + 1) * (
        reduction_stage_count + 2
    )
    second_pass_base = after_first_base + reduction_stage_count + 1
    h_next_base = second_pass_base + (column_index + 1) * (reduction_stage_count + 2)
    update_base = h_next_base + reduction_stage_count + 4
    metrics_base = update_base + reduction_stage_count + 4
    checkpoint_base = metrics_base + 4 * reduction_stage_count
    expected_end = column_schedule_base + _global_column_schedule_stride(
        reduction_stage_count,
        column_index,
    )
    if checkpoint_base + 3 != expected_end:  # pragma: no cover - algebraic seal
        raise _launch_contract_error(
            "the fixed global column schedule formulas are inconsistent."
        )
    return (
        first_pass_base,
        after_first_base,
        second_pass_base,
        h_next_base,
        update_base,
        metrics_base,
        checkpoint_base,
    )


def _positive_int32(value: Any, label: str) -> int:
    return _bounded_int(value, label, minimum=1)


def _schedule_epoch(value: Any) -> int:
    return _bounded_int(
        value,
        "expected_schedule_epoch",
        minimum=0,
        maximum=_INT32_MAX - 1,
    )


def _exact_enum(value: Any, label: str, allowed: frozenset[int]) -> int:
    if type(value) is not int or value not in allowed:
        raise _launch_contract_error(
            f"{label} is unavailable in the implemented recurrence-v2 slice."
        )
    return value


def _bounded_int(
    value: Any,
    label: str,
    *,
    minimum: int,
    maximum: int = _INT32_MAX,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _launch_contract_error(
            f"{label} must be a signed int32 in [{minimum}, {maximum}]."
        )
    return value


def _finite_float64(value: Any, label: str) -> float:
    if type(value) not in (int, float):
        raise _launch_contract_error(f"{label} must be an exact int or float.")
    try:
        converted = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise _launch_contract_error(f"{label} must fit finite float64.") from exc
    if not math.isfinite(converted):
        raise _launch_contract_error(f"{label} must be finite float64.")
    return converted


def _nonnegative_float64(value: Any, label: str) -> float:
    converted = _finite_float64(value, label)
    if converted < 0.0:
        raise _launch_contract_error(f"{label} must be nonnegative.")
    return converted


def _positive_float64(value: Any, label: str) -> float:
    converted = _finite_float64(value, label)
    if converted <= 0.0:
        raise _launch_contract_error(f"{label} must be positive.")
    return converted


def _vector_block_count(value_count: int) -> int:
    return (value_count + HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE - 1) // (
        HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE
    )


def _pointer_arguments(values: tuple[tuple[str, Any], ...]) -> tuple[int, ...]:
    return tuple(_runtime_pointer(value, label) for label, value in values)


def _runtime_pointer(value: Any, label: str) -> int:
    try:
        pointer = _pointer_integer(value, label)
    except HipRtcError as exc:
        raise _launch_contract_error(exc.message) from exc
    if pointer > _UINTPTR_MAX or ctypes.c_void_p(pointer).value != pointer:
        raise _launch_contract_error(
            f"{label} does not fit the native uintptr capacity."
        )
    return pointer


def _launch_contract_error(message: str) -> HipRtcFgmresV2Error:
    return HipRtcFgmresV2Error(
        "hip_rtc_fgmres_v2_launch_contract_invalid",
        message,
        launch_disposition="not_attempted",
    )


__all__ = [
    "HIP_RTC_FGMRES_V2_ABI_VERSION",
    "HIP_RTC_FGMRES_V2_CONTROL_BLOCK_SIZE",
    "HIP_RTC_FGMRES_V2_CONTROL_STATE_BYTES",
    "HIP_RTC_FGMRES_V2_CONTROL_SYMBOL",
    "HIP_RTC_FGMRES_V2_CSR_SPMV_INDEXED_SYMBOL",
    "HIP_RTC_FGMRES_V2_IDENTITY_SCHEMA_VERSION",
    "HIP_RTC_FGMRES_V2_KERNEL_NAME",
    "HIP_RTC_FGMRES_V2_REDUCE_SYMBOL",
    "HIP_RTC_FGMRES_V2_REDUCTION_VALUES_PER_BLOCK",
    "HIP_RTC_FGMRES_V2_VECTOR_BLOCK_SIZE",
    "HIP_RTC_FGMRES_V2_VECTOR_SYMBOL",
    "FgmresV2FirstColumnCandidatePreparationLaunch",
    "FgmresV2FirstColumnCandidateResidualLaunch",
    "FgmresV2FirstColumnCandidateScaleMetricsLaunch",
    "FgmresV2CanonicalPredecessorLaunch",
    "FgmresV2FirstColumnPredecessorValidationLaunch",
    "FgmresV2FirstColumnCheckpointTransactionLaunch",
    "FgmresV2FirstColumnCompletionLaunch",
    "FgmresV2FirstColumnReductionLaunch",
    "FgmresV2InitialReductionLaunch",
    "HipRtcFgmresV2Error",
    "HipRtcFgmresV2Kernel",
    "HipRtcFgmresV2KernelIdentity",
    "compile_hip_rtc_fgmres_v2_kernel",
    "canonical_first_column_predecessor_launches_v2",
    "first_column_candidate_preparation_launches_v2",
    "first_column_candidate_residual_launches_v2",
    "first_column_candidate_scale_metrics_launches_v2",
    "first_column_checkpoint_transaction_launches_v2",
    "first_column_completion_launches_v2",
    "first_column_predecessor_validation_launch_v2",
    "first_column_reduction_launches_v2",
    "initial_reduction_launches_v2",
    "reduction_output_count_v2",
    "reduction_stage_output_counts_v2",
    "solve_record_byte_length_v2",
]
