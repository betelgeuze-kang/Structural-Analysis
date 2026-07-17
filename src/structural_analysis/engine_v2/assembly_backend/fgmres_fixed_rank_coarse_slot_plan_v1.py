"""Typed fixed-rank coarse recurrence-slot source contract v1.

The historical recurrence-v2 and fixed-rank coarse-v1 sources stay byte
identical.  This module composes them with one small supplement in a single
HIPRTC translation unit.  The supplement replaces one logical
``APPLY_JACOBI_INDEXED`` operation with four ordered physical launches:
schedule gate, coarse dot, bounded solve, and slot-aware apply.

This is a compile-time source/ABI contract only.  It does not load a module,
mutate a live recurrence, observe device status, or claim solver parity.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_context_v2 import (
    HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
    HIP_FGMRES_RTC_SOURCE_SHA256_V2,
)
from .fgmres_fixed_rank_coarse_plan_v1 import (
    HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
    hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1,
)


HIP_FGMRES_FIXED_RANK_COARSE_SLOT_PLAN_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-fixed-rank-coarse-slot-plan.v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_CAPABILITY_PROFILE_V1 = (
    "phase0_typed_fixed_rank_coarse_recurrence_slot_source_contract"
)
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLICATION_ABI_VERSION_V1 = 1
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_GATE_SYMBOL_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_slot_gate_v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLY_SYMBOL_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_slot_apply_v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1 = (
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_GATE_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_DOT_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SOLVE_SYMBOL_V1,
    HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLY_SYMBOL_V1,
)
HIP_FGMRES_FIXED_RANK_COARSE_SLOT_COMPILE_OPTIONS_V1 = (
    "-O3",
    "-std=c++17",
    "-ffp-contract=off",
)

_KERNEL_DIRECTORY = Path(__file__).with_name("kernels")
_RECURRENCE_RESOURCE = "kernels/engine_v2_fgmres_v2.hip.cpp"
_COARSE_RESOURCE = "kernels/engine_v2_fgmres_fixed_rank_coarse_v1.hip.cpp"
_SLOT_RESOURCE = "kernels/engine_v2_fgmres_fixed_rank_coarse_slot_v1.hip.cpp"
_RECURRENCE_PATH = _KERNEL_DIRECTORY / Path(_RECURRENCE_RESOURCE).name
_COARSE_PATH = _KERNEL_DIRECTORY / Path(_COARSE_RESOURCE).name
_SLOT_PATH = _KERNEL_DIRECTORY / Path(_SLOT_RESOURCE).name
_COARSE_NAMESPACE_OPEN = b"namespace engine_v2_coarse_v1 {\n"
_COARSE_NAMESPACE_CLOSE = b"}  // namespace engine_v2_coarse_v1\n"


class HipFgmresFixedRankCoarseSlotPlanV1Error(ValueError):
    """Raised when a frozen source component or slot contract drifts."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


def hip_fgmres_fixed_rank_coarse_slot_source_components_v1() -> dict[str, Any]:
    """Return fresh hashes for the exact three package-owned components."""

    recurrence, coarse, slot = _source_components()
    combined = _compose_source(recurrence, coarse, slot)
    return {
        "recurrence": {
            "resource": _RECURRENCE_RESOURCE,
            "sha256": _sha256(recurrence),
            "byte_length": len(recurrence),
        },
        "coarse": {
            "resource": _COARSE_RESOURCE,
            "sha256": _sha256(coarse),
            "byte_length": len(coarse),
            "composition_namespace": "engine_v2_coarse_v1",
        },
        "slot": {
            "resource": _SLOT_RESOURCE,
            "sha256": _sha256(slot),
            "byte_length": len(slot),
        },
        "combined": {
            "program_name": Path(_SLOT_RESOURCE).name,
            "sha256": _sha256(combined),
            "byte_length": len(combined),
        },
    }


def hip_fgmres_fixed_rank_coarse_slot_kernel_abi_payload_v1() -> dict[str, Any]:
    """Return the dimension-independent typed-slot ABI payload."""

    components = hip_fgmres_fixed_rank_coarse_slot_source_components_v1()
    return {
        "schema_version": HIP_FGMRES_FIXED_RANK_COARSE_SLOT_PLAN_SCHEMA_VERSION_V1,
        "capability_profile": (HIP_FGMRES_FIXED_RANK_COARSE_SLOT_CAPABILITY_PROFILE_V1),
        "application_abi_version": (
            HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLICATION_ABI_VERSION_V1
        ),
        "frozen_recurrence_abi_hash": HIP_FGMRES_COMBINED_RECURRENCE_ABI_HASH_V2,
        "frozen_recurrence_source_sha256": HIP_FGMRES_RTC_SOURCE_SHA256_V2,
        "frozen_coarse_application_abi_hash": canonical_hash(
            hip_fgmres_fixed_rank_coarse_kernel_abi_payload_v1()
        ),
        "source_components": components,
        "compile_options": list(HIP_FGMRES_FIXED_RANK_COARSE_SLOT_COMPILE_OPTIONS_V1),
        "logical_operation": {
            "schedule_row": "APPLY_JACOBI_INDEXED",
            "selected_kind": "fixed_rank_coarse",
            "logical_operation_count": 1,
            "jacobi_kernel_launch_count": 0,
            "recurrence_schedule_epoch_claim_count": 1,
            "recurrence_pending_reservation_count": 1,
        },
        "physical_launches": {
            "count": 4,
            "symbols": list(HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1),
            "order": [
                "admit_coordinate_claim_epoch_initialize_workspace",
                "deterministic_block_tree_coarse_dot",
                "single_thread_bounded_cholesky_solve",
                "row_parallel_coarse_plus_jacobi_smoothing_apply",
            ],
            "same_stream_required": True,
            "intermediate_synchronization_count": 0,
        },
        "inactive_padding": {
            "device_status_bit": 31,
            "host_branch_required": False,
            "schedule_epoch_claimed": False,
            "numeric_inputs_read": False,
            "preconditioned_basis_z_written": False,
        },
        "status_bits": {
            "invalid_geometry": 0,
            "nonfinite_input": 1,
            "nonpositive_factor": 2,
            "nonfinite_arithmetic": 3,
            "slot_gate_failure": 4,
            "inactive_padding": 31,
        },
        "claim_boundary": {
            "compile_time_source_contract_only": True,
            "historical_recurrence_source_changed": False,
            "historical_coarse_source_changed": False,
            "logical_jacobi_row_replaced_in_source_contract": True,
            "live_runtime_integration_performed": False,
            "coarse_device_status_directly_terminal_bound": False,
            "actual_device_execution_performed": False,
            "full_solve_numerical_parity_proven": False,
            "full_iteration_host_copy_zero_proven": False,
            "end_to_end_o_n_proven": False,
            "speedup_proven": False,
            "promotion_eligible": False,
            "commercial_ready": False,
        },
    }


def hip_fgmres_fixed_rank_coarse_slot_source_v1() -> bytes:
    """Return fresh combined source after validating frozen component identity."""

    recurrence, coarse, slot = _source_components()
    if _sha256(recurrence) != HIP_FGMRES_RTC_SOURCE_SHA256_V2:
        _fail(
            "hip_fgmres_coarse_slot_recurrence_source_changed",
            "/source_components/recurrence/sha256",
        )
    source = _compose_source(recurrence, coarse, slot)
    payload = hip_fgmres_fixed_rank_coarse_slot_kernel_abi_payload_v1()
    combined = payload["source_components"]["combined"]
    if combined["sha256"] != _sha256(source) or combined["byte_length"] != len(source):
        _fail(
            "hip_fgmres_coarse_slot_combined_source_changed",
            "/source_components/combined",
        )
    return bytes(source)


def hip_fgmres_fixed_rank_coarse_slot_kernel_abi_hash_v1() -> str:
    """Return the canonical typed-slot ABI hash."""

    return canonical_hash(hip_fgmres_fixed_rank_coarse_slot_kernel_abi_payload_v1())


def _source_components() -> tuple[bytes, bytes, bytes]:
    rows: list[bytes] = []
    for path, label in (
        (_RECURRENCE_PATH, "recurrence"),
        (_COARSE_PATH, "coarse"),
        (_SLOT_PATH, "slot"),
    ):
        try:
            source = path.read_bytes()
        except OSError as exc:
            raise HipFgmresFixedRankCoarseSlotPlanV1Error(
                "hip_fgmres_coarse_slot_source_missing",
                f"/source_components/{label}",
                type(exc).__name__,
            ) from exc
        if not source or b"\x00" in source:
            _fail(
                "hip_fgmres_coarse_slot_source_invalid",
                f"/source_components/{label}",
            )
        rows.append(source)
    return rows[0], rows[1], rows[2]


def _compose_source(recurrence: bytes, coarse: bytes, slot: bytes) -> bytes:
    return b"".join(
        (
            recurrence,
            b"\n",
            _COARSE_NAMESPACE_OPEN,
            coarse,
            b"\n",
            _COARSE_NAMESPACE_CLOSE,
            slot,
        )
    )


def _sha256(source: bytes) -> str:
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipFgmresFixedRankCoarseSlotPlanV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLICATION_ABI_VERSION_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_APPLY_SYMBOL_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_COMPILE_OPTIONS_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_GATE_SYMBOL_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_KERNEL_SYMBOLS_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_SLOT_PLAN_SCHEMA_VERSION_V1",
    "HipFgmresFixedRankCoarseSlotPlanV1Error",
    "hip_fgmres_fixed_rank_coarse_slot_kernel_abi_hash_v1",
    "hip_fgmres_fixed_rank_coarse_slot_kernel_abi_payload_v1",
    "hip_fgmres_fixed_rank_coarse_slot_source_components_v1",
    "hip_fgmres_fixed_rank_coarse_slot_source_v1",
]
