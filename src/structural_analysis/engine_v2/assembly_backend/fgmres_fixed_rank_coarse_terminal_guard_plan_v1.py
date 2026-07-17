"""Frozen-source contract for device-side coarse terminal publication v1."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_context_v2 import HIP_FGMRES_RTC_SOURCE_SHA256_V2


HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_PLAN_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-fixed-rank-coarse-terminal-guard-plan.v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_CAPABILITY_PROFILE_V1 = (
    "phase0_device_direct_coarse_terminal_publication"
)
HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_ABI_VERSION_V1 = 1
HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1 = (
    "engine_v2_fgmres_fixed_rank_coarse_terminal_guard_v1"
)
HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1 = (
    "-O3",
    "-std=c++17",
    "-ffp-contract=off",
)

_KERNEL_DIRECTORY = Path(__file__).with_name("kernels")
_RECURRENCE_RESOURCE = "kernels/engine_v2_fgmres_v2.hip.cpp"
_GUARD_RESOURCE = "kernels/engine_v2_fgmres_fixed_rank_coarse_terminal_guard_v1.hip.cpp"
_RECURRENCE_PATH = _KERNEL_DIRECTORY / Path(_RECURRENCE_RESOURCE).name
_GUARD_PATH = _KERNEL_DIRECTORY / Path(_GUARD_RESOURCE).name


class HipFgmresFixedRankCoarseTerminalGuardPlanV1Error(ValueError):
    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


def hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1() -> dict[
    str, Any
]:
    recurrence, guard = _source_components()
    combined = _compose_source(recurrence, guard)
    return {
        "recurrence": {
            "resource": _RECURRENCE_RESOURCE,
            "sha256": _sha256(recurrence),
            "byte_length": len(recurrence),
        },
        "guard": {
            "resource": _GUARD_RESOURCE,
            "sha256": _sha256(guard),
            "byte_length": len(guard),
        },
        "combined": {
            "program_name": Path(_GUARD_RESOURCE).name,
            "sha256": _sha256(combined),
            "byte_length": len(combined),
        },
    }


def hip_fgmres_fixed_rank_coarse_terminal_guard_abi_payload_v1() -> dict[str, Any]:
    return {
        "schema_version": (
            HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_PLAN_SCHEMA_VERSION_V1
        ),
        "capability_profile": (
            HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_CAPABILITY_PROFILE_V1
        ),
        "abi_version": HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_ABI_VERSION_V1,
        "symbol": HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1,
        "compile_options": list(
            HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1
        ),
        "source_components": (
            hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1()
        ),
        "launch": {
            "grid": [1, 1, 1],
            "block": [1, 1, 1],
            "same_stream_after_typed_slot_apply": True,
            "arguments": [
                "coarse_status",
                "fgmres_control_state_v2",
                "solve_record",
            ],
        },
        "status_mapping": {
            "inactive_bit_31": "exact_value_no_op_mixed_bits_fail_closed",
            "invalid_geometry_or_gate_failure": "invalid_control_or_geometry",
            "nonfinite_input": "nonfinite_input",
            "nonpositive_factor": "jacobi_inverse",
            "nonfinite_arithmetic": "arithmetic_overflow",
            "failure_origin": "vector",
            "termination": "orthogonalization_failed",
            "first_device_error_wins": True,
        },
        "claim_boundary": {
            "device_direct_terminal_publication_implemented": True,
            "coarse_device_status_directly_terminal_bound": True,
            "host_copy_count": 0,
            "host_branch_count": 0,
            "intermediate_synchronization_count": 0,
            "live_recurrence_integration_performed": True,
            "actual_device_execution_performed": True,
            "full_solve_numerical_parity_proven": False,
            "full_iteration_host_copy_zero_proven": False,
            "end_to_end_o_n_proven": False,
            "speedup_proven": False,
            "promotion_eligible": False,
            "commercial_ready": False,
        },
    }


def hip_fgmres_fixed_rank_coarse_terminal_guard_abi_hash_v1() -> str:
    return canonical_hash(hip_fgmres_fixed_rank_coarse_terminal_guard_abi_payload_v1())


def hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1() -> bytes:
    recurrence, guard = _source_components()
    if _sha256(recurrence) != HIP_FGMRES_RTC_SOURCE_SHA256_V2:
        _fail(
            "hip_fgmres_coarse_terminal_guard_recurrence_source_changed",
            "/source_components/recurrence/sha256",
        )
    source = _compose_source(recurrence, guard)
    components = hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1()
    if components["combined"]["sha256"] != _sha256(source) or components["combined"][
        "byte_length"
    ] != len(source):
        _fail(
            "hip_fgmres_coarse_terminal_guard_combined_source_changed",
            "/source_components/combined",
        )
    return bytes(source)


def _source_components() -> tuple[bytes, bytes]:
    rows: list[bytes] = []
    for path, label in (
        (_RECURRENCE_PATH, "recurrence"),
        (_GUARD_PATH, "guard"),
    ):
        try:
            source = path.read_bytes()
        except OSError as exc:
            raise HipFgmresFixedRankCoarseTerminalGuardPlanV1Error(
                "hip_fgmres_coarse_terminal_guard_source_missing",
                f"/source_components/{label}",
                type(exc).__name__,
            ) from exc
        if not source or b"\x00" in source:
            _fail(
                "hip_fgmres_coarse_terminal_guard_source_invalid",
                f"/source_components/{label}",
            )
        rows.append(source)
    return rows[0], rows[1]


def _compose_source(recurrence: bytes, guard: bytes) -> bytes:
    return b"".join((recurrence, b"\n", guard))


def _sha256(source: bytes) -> str:
    return "sha256:" + hashlib.sha256(source).hexdigest()


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipFgmresFixedRankCoarseTerminalGuardPlanV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_ABI_VERSION_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_COMPILE_OPTIONS_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_PLAN_SCHEMA_VERSION_V1",
    "HIP_FGMRES_FIXED_RANK_COARSE_TERMINAL_GUARD_SYMBOL_V1",
    "HipFgmresFixedRankCoarseTerminalGuardPlanV1Error",
    "hip_fgmres_fixed_rank_coarse_terminal_guard_abi_hash_v1",
    "hip_fgmres_fixed_rank_coarse_terminal_guard_abi_payload_v1",
    "hip_fgmres_fixed_rank_coarse_terminal_guard_source_components_v1",
    "hip_fgmres_fixed_rank_coarse_terminal_guard_source_v1",
]
