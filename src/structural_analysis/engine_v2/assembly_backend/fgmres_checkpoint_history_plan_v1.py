"""Additive device ABI for committed FGMRES checkpoint vector history.

The recurrence-v2 solve record deliberately stores only scalar restart rows.
This module leaves that frozen ABI untouched and describes two companion
device blobs.  Each blob contains a small little-endian publication header,
one fixed metadata row per restart slot, and row-major FP64 vector payloads.

The matching capture kernel publishes a row marker only after every vector
lane has finished copying.  A detached consumer can therefore reject a
partial or conflicting capture without interpreting uncommitted bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Literal

from jsonschema import Draft202012Validator
import numpy as np

from structural_analysis.engine_v2.contracts._canonical import canonical_hash

from .fgmres_plan import HIP_FGMRES_MAX_ITERATIONS


HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_SCHEMA_VERSION_V1 = (
    "structural-analysis-hip-fgmres-checkpoint-history-plan.v1"
)
HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_CAPABILITY_PROFILE_V1 = (
    "phase0_hip_fgmres_committed_checkpoint_vector_history_plan"
)
HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1 = 1
HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1 = 64
HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1 = 32
HIP_FGMRES_CHECKPOINT_HISTORY_MAGIC_V1 = 0x31485246  # ASCII "FRH1".
HIP_FGMRES_CHECKPOINT_HISTORY_SOLUTION_ROLE_CODE_V1 = 1
HIP_FGMRES_CHECKPOINT_HISTORY_TRUE_RESIDUAL_ROLE_CODE_V1 = 2
HIP_FGMRES_CHECKPOINT_HISTORY_BLOCK_SIZE_V1 = 256

_ZERO_HASH = "sha256:" + "0" * 64
_INT32_MAX = (1 << 31) - 1
_UINT64_MAX = (1 << 64) - 1
_ROLES = ("checkpoint_solution_history", "checkpoint_true_residual_history")
_ROLE_CODES = {
    "checkpoint_solution_history": (
        HIP_FGMRES_CHECKPOINT_HISTORY_SOLUTION_ROLE_CODE_V1
    ),
    "checkpoint_true_residual_history": (
        HIP_FGMRES_CHECKPOINT_HISTORY_TRUE_RESIDUAL_ROLE_CODE_V1
    ),
}
_SCHEMA_RESOURCE = "hip_fgmres_checkpoint_history_plan_v1.schema.json"
_HEADER_FIELD_NAMES = (
    "magic",
    "abi_version",
    "role_code",
    "initialized",
    "free_dof_count",
    "maximum_restart_count",
    "header_bytes",
    "restart_bytes",
    "payload_offset_bytes",
    "payload_byte_count_low_u32",
    "payload_byte_count_high_u32",
    "capture_launch_count",
    "populated_restart_count",
    "device_error_bits",
    "reserved_i32_0",
    "reserved_i32_1",
)
_RESTART_FIELD_NAMES = (
    "captured",
    "restart_index",
    "column_index",
    "end_iteration",
    "source_restart_flags",
    "source_terminal_status",
    "source_termination_code",
    "reserved_i32_0",
)


class HipFgmresCheckpointHistoryPlanV1Error(ValueError):
    """Stable validation error for the additive history plan/blob ABI."""

    def __init__(self, code: str, path: str, message: str = "") -> None:
        self.code = code
        self.path = path
        self.message = message or code
        super().__init__(f"{code}@{path}: {self.message}")


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryBufferPlanV1:
    role: Literal[
        "checkpoint_solution_history",
        "checkpoint_true_residual_history",
    ]
    role_code: int
    dtype: Literal["|u1"]
    byte_length: int
    payload_offset_bytes: int
    payload_shape: tuple[int, int]
    payload_dtype: Literal["<f8"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "role_code": self.role_code,
            "dtype": self.dtype,
            "byte_length": self.byte_length,
            "payload_offset_bytes": self.payload_offset_bytes,
            "payload_shape": list(self.payload_shape),
            "payload_dtype": self.payload_dtype,
        }


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryPlanV1:
    schema_version: str
    capability_profile: str
    blob_abi_version: int
    free_dof_count: int
    maximum_restart_count: int
    header_bytes: int
    restart_bytes: int
    payload_offset_bytes: int
    payload_byte_count: int
    blob_byte_count: int
    buffers: tuple[HipFgmresCheckpointHistoryBufferPlanV1, ...]
    abi_hash: str
    plan_hash: str

    @property
    def owned_device_byte_length(self) -> int:
        return 2 * self.blob_byte_count

    def buffer(self, role: str) -> HipFgmresCheckpointHistoryBufferPlanV1:
        for row in self.buffers:
            if row.role == role:
                return row
        raise KeyError(role)

    def to_dict(self) -> dict[str, Any]:
        validate_hip_fgmres_checkpoint_history_plan_v1(self)
        return _plan_payload(self, include_hash=True)

    def to_manifest(self) -> dict[str, Any]:
        return self.to_dict()


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryRestartRowV1:
    captured: int
    restart_index: int
    column_index: int
    end_iteration: int
    source_restart_flags: int
    source_terminal_status: int
    source_termination_code: int
    reserved_i32_0: int

    def to_dict(self) -> dict[str, int]:
        return {name: int(getattr(self, name)) for name in _RESTART_FIELD_NAMES}


@dataclass(frozen=True, slots=True)
class HipFgmresCheckpointHistoryBlobV1:
    role: Literal[
        "checkpoint_solution_history",
        "checkpoint_true_residual_history",
    ]
    free_dof_count: int
    maximum_restart_count: int
    capture_launch_count: int
    populated_restart_count: int
    device_error_bits: int
    restart_rows: tuple[HipFgmresCheckpointHistoryRestartRowV1, ...]
    vector_payload: bytes
    payload_sha256: str

    @property
    def vector_array(self) -> np.ndarray:
        return np.frombuffer(self.vector_payload, dtype="<f8").reshape(
            self.maximum_restart_count,
            self.free_dof_count,
        )


def hip_fgmres_checkpoint_history_blob_abi_payload_v1() -> dict[str, Any]:
    """Return the dimension-independent, hashable companion blob ABI."""

    return {
        "abi_version": HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1,
        "byte_order": "little_endian",
        "magic_u32": HIP_FGMRES_CHECKPOINT_HISTORY_MAGIC_V1,
        "header_bytes": HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1,
        "restart_bytes": HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1,
        "header_layout": "16*i32",
        "restart_layout": "8*i32",
        "header_fields": [
            {"name": name, "dtype": "i32", "offset_bytes": 4 * index}
            for index, name in enumerate(_HEADER_FIELD_NAMES)
        ],
        "restart_fields": [
            {"name": name, "dtype": "i32", "offset_bytes": 4 * index}
            for index, name in enumerate(_RESTART_FIELD_NAMES)
        ],
        "roles": [{"name": role, "role_code": _ROLE_CODES[role]} for role in _ROLES],
        "payload": {
            "dtype": "<f8",
            "layout": "row_major_restart_by_free_dof",
            "shape": ["maximum_restart_count", "free_dof_count"],
            "payload_offset_formula": "64+32*R",
            "payload_byte_formula": "8*R*F",
            "blob_byte_formula": "64+32*R+8*R*F",
        },
        "publication": {
            "initialization": "zero_entire_blob_then_publish_header",
            "copy": "one_block_strided_exact_fp64_bit_copy",
            "row_marker_order": "threadfence_then_metadata_then_captured_last",
            "inactive_or_unpublished_source": "no_payload_or_row_write",
            "conflicting_duplicate": "device_error_bit_and_no_overwrite",
        },
    }


def compile_hip_fgmres_checkpoint_history_plan_v1(
    free_dof_count: int,
    maximum_restart_count: int,
) -> HipFgmresCheckpointHistoryPlanV1:
    """Compile two fixed companion blob extents without allocating memory."""

    f = _positive_int32(free_dof_count, "/free_dof_count")
    r = _bounded_positive_int(
        maximum_restart_count,
        "/maximum_restart_count",
        HIP_FGMRES_MAX_ITERATIONS,
    )
    payload_offset = (
        HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1
        + HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1 * r
    )
    payload_bytes = _checked_u64_product(8, r, f, path="/payload_byte_count")
    blob_bytes = _checked_u64_sum(
        payload_offset,
        payload_bytes,
        path="/blob_byte_count",
    )
    if payload_offset % 8 or blob_bytes % 8:
        _fail(
            "hip_fgmres_checkpoint_history_alignment_invalid",
            "/blob_byte_count",
        )
    buffers = tuple(
        HipFgmresCheckpointHistoryBufferPlanV1(
            role=role,  # type: ignore[arg-type]
            role_code=_ROLE_CODES[role],
            dtype="|u1",
            byte_length=blob_bytes,
            payload_offset_bytes=payload_offset,
            payload_shape=(r, f),
            payload_dtype="<f8",
        )
        for role in _ROLES
    )
    abi_hash = canonical_hash(hip_fgmres_checkpoint_history_blob_abi_payload_v1())
    draft = HipFgmresCheckpointHistoryPlanV1(
        schema_version=HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_SCHEMA_VERSION_V1,
        capability_profile=(HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_CAPABILITY_PROFILE_V1),
        blob_abi_version=HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1,
        free_dof_count=f,
        maximum_restart_count=r,
        header_bytes=HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1,
        restart_bytes=HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1,
        payload_offset_bytes=payload_offset,
        payload_byte_count=payload_bytes,
        blob_byte_count=blob_bytes,
        buffers=buffers,
        abi_hash=abi_hash,
        plan_hash=_ZERO_HASH,
    )
    result = replace(
        draft,
        plan_hash=canonical_hash(_plan_payload(draft, include_hash=False)),
    )
    return validate_hip_fgmres_checkpoint_history_plan_v1(result)


def validate_hip_fgmres_checkpoint_history_plan_v1(
    plan: HipFgmresCheckpointHistoryPlanV1,
) -> HipFgmresCheckpointHistoryPlanV1:
    if type(plan) is not HipFgmresCheckpointHistoryPlanV1:
        _fail("hip_fgmres_checkpoint_history_plan_type_invalid", "/")
    # Avoid recursion: reconstruct the deterministic fields directly.
    f = _positive_int32(plan.free_dof_count, "/free_dof_count")
    r = _bounded_positive_int(
        plan.maximum_restart_count,
        "/maximum_restart_count",
        HIP_FGMRES_MAX_ITERATIONS,
    )
    offset = HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1 + 32 * r
    payload_bytes = _checked_u64_product(8, r, f, path="/payload_byte_count")
    blob_bytes = _checked_u64_sum(offset, payload_bytes, path="/blob_byte_count")
    expected_buffers = tuple(
        HipFgmresCheckpointHistoryBufferPlanV1(
            role=role,  # type: ignore[arg-type]
            role_code=_ROLE_CODES[role],
            dtype="|u1",
            byte_length=blob_bytes,
            payload_offset_bytes=offset,
            payload_shape=(r, f),
            payload_dtype="<f8",
        )
        for role in _ROLES
    )
    if (
        plan.schema_version != HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_SCHEMA_VERSION_V1
        or plan.capability_profile
        != HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_CAPABILITY_PROFILE_V1
        or plan.blob_abi_version != HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1
        or plan.header_bytes != HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1
        or plan.restart_bytes != HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1
        or plan.payload_offset_bytes != offset
        or plan.payload_byte_count != payload_bytes
        or plan.blob_byte_count != blob_bytes
        or plan.buffers != expected_buffers
        or plan.abi_hash
        != canonical_hash(hip_fgmres_checkpoint_history_blob_abi_payload_v1())
        or plan.plan_hash != canonical_hash(_plan_payload(plan, include_hash=False))
    ):
        _fail("hip_fgmres_checkpoint_history_plan_invalid", "/")
    _validate_schema(_plan_payload(plan, include_hash=True))
    return plan


def decode_hip_fgmres_checkpoint_history_blob_v1(
    payload: bytes,
    *,
    expected_role: Literal[
        "checkpoint_solution_history",
        "checkpoint_true_residual_history",
    ],
    expected_free_dof_count: int,
    expected_maximum_restart_count: int,
) -> HipFgmresCheckpointHistoryBlobV1:
    """Decode one detached blob and reject partial/conflicting publication."""

    if type(payload) is not bytes:
        _fail("hip_fgmres_checkpoint_history_blob_type_invalid", "/payload")
    if expected_role not in _ROLE_CODES:
        _fail("hip_fgmres_checkpoint_history_role_invalid", "/expected_role")
    plan = compile_hip_fgmres_checkpoint_history_plan_v1(
        expected_free_dof_count,
        expected_maximum_restart_count,
    )
    if len(payload) != plan.blob_byte_count:
        _fail("hip_fgmres_checkpoint_history_blob_extent_invalid", "/payload")
    header = struct.unpack_from("<16i", payload, 0)
    payload_bytes_from_header = (header[10] & 0xFFFFFFFF) << 32 | (
        header[9] & 0xFFFFFFFF
    )
    if (
        (header[0] & 0xFFFFFFFF) != HIP_FGMRES_CHECKPOINT_HISTORY_MAGIC_V1
        or header[1] != HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1
        or header[2] != _ROLE_CODES[expected_role]
        or header[3] != 1
        or header[4] != plan.free_dof_count
        or header[5] != plan.maximum_restart_count
        or header[6] != plan.header_bytes
        or header[7] != plan.restart_bytes
        or header[8] != plan.payload_offset_bytes
        or payload_bytes_from_header != plan.payload_byte_count
        or header[11] < 0
        or not 0 <= header[12] <= plan.maximum_restart_count
        or header[13] != 0
        or header[14] != 0
        or header[15] != 0
    ):
        _fail("hip_fgmres_checkpoint_history_blob_header_invalid", "/header")
    rows: list[HipFgmresCheckpointHistoryRestartRowV1] = []
    captured_count = 0
    for index in range(plan.maximum_restart_count):
        values = struct.unpack_from(
            "<8i",
            payload,
            plan.header_bytes + index * plan.restart_bytes,
        )
        row = HipFgmresCheckpointHistoryRestartRowV1(*values)
        if row.captured == 0:
            if any(values[1:]):
                _fail(
                    "hip_fgmres_checkpoint_history_unpublished_row_dirty",
                    f"/restart_rows/{index}",
                )
        elif (
            row.captured != 1
            or row.restart_index != index + 1
            or row.column_index < 0
            or row.end_iteration <= 0
            or row.source_restart_flags < 0
            or row.source_terminal_status < 0
            or row.source_termination_code < 0
            or row.reserved_i32_0 != 0
        ):
            _fail(
                "hip_fgmres_checkpoint_history_restart_row_invalid",
                f"/restart_rows/{index}",
            )
        else:
            captured_count += 1
        rows.append(row)
    if captured_count != header[12]:
        _fail(
            "hip_fgmres_checkpoint_history_population_count_invalid",
            "/header/populated_restart_count",
        )
    vector_payload = payload[plan.payload_offset_bytes :]
    return HipFgmresCheckpointHistoryBlobV1(
        role=expected_role,
        free_dof_count=plan.free_dof_count,
        maximum_restart_count=plan.maximum_restart_count,
        capture_launch_count=header[11],
        populated_restart_count=header[12],
        device_error_bits=header[13],
        restart_rows=tuple(rows),
        vector_payload=vector_payload,
        payload_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
    )


def validate_hip_fgmres_checkpoint_history_blob_pair_v1(
    solution_payload: bytes,
    true_residual_payload: bytes,
    *,
    expected_free_dof_count: int,
    expected_maximum_restart_count: int,
    expected_capture_launch_count: int | None = None,
) -> tuple[HipFgmresCheckpointHistoryBlobV1, HipFgmresCheckpointHistoryBlobV1]:
    solution = decode_hip_fgmres_checkpoint_history_blob_v1(
        solution_payload,
        expected_role="checkpoint_solution_history",
        expected_free_dof_count=expected_free_dof_count,
        expected_maximum_restart_count=expected_maximum_restart_count,
    )
    residual = decode_hip_fgmres_checkpoint_history_blob_v1(
        true_residual_payload,
        expected_role="checkpoint_true_residual_history",
        expected_free_dof_count=expected_free_dof_count,
        expected_maximum_restart_count=expected_maximum_restart_count,
    )
    if (
        solution.capture_launch_count != residual.capture_launch_count
        or solution.populated_restart_count != residual.populated_restart_count
        or solution.device_error_bits != residual.device_error_bits
        or solution.restart_rows != residual.restart_rows
    ):
        _fail("hip_fgmres_checkpoint_history_blob_pair_mismatch", "/")
    if (
        expected_capture_launch_count is not None
        and solution.capture_launch_count != expected_capture_launch_count
    ):
        _fail(
            "hip_fgmres_checkpoint_history_capture_count_invalid",
            "/header/capture_launch_count",
        )
    return solution, residual


def _plan_payload(
    plan: HipFgmresCheckpointHistoryPlanV1,
    *,
    include_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": plan.schema_version,
        "capability_profile": plan.capability_profile,
        "blob_abi_version": plan.blob_abi_version,
        "dimensions": {
            "free_dof_count": plan.free_dof_count,
            "maximum_restart_count": plan.maximum_restart_count,
        },
        "layout": {
            "header_bytes": plan.header_bytes,
            "restart_bytes": plan.restart_bytes,
            "payload_offset_bytes": plan.payload_offset_bytes,
            "payload_byte_count": plan.payload_byte_count,
            "blob_byte_count": plan.blob_byte_count,
            "owned_device_byte_length": plan.owned_device_byte_length,
        },
        "buffers": [row.to_dict() for row in plan.buffers],
        "abi_hash": plan.abi_hash,
    }
    if include_hash:
        payload["plan_hash"] = plan.plan_hash
    return payload


def _positive_int32(value: Any, path: str) -> int:
    if type(value) is not int or not 0 < value <= _INT32_MAX:
        _fail("hip_fgmres_checkpoint_history_dimension_invalid", path)
    return value


def _bounded_positive_int(value: Any, path: str, upper: int) -> int:
    if type(value) is not int or not 0 < value <= upper:
        _fail("hip_fgmres_checkpoint_history_dimension_invalid", path)
    return value


def _checked_u64_product(*values: int, path: str) -> int:
    result = 1
    for value in values:
        if value < 0 or (value and result > _UINT64_MAX // value):
            _fail("hip_fgmres_checkpoint_history_extent_overflow", path)
        result *= value
    return result


def _checked_u64_sum(left: int, right: int, *, path: str) -> int:
    if left < 0 or right < 0 or left > _UINT64_MAX - right:
        _fail("hip_fgmres_checkpoint_history_extent_overflow", path)
    return left + right


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = Path(__file__).parents[2] / "schemas" / _SCHEMA_RESOURCE
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_schema(payload: dict[str, Any]) -> None:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("hip_fgmres_checkpoint_history_plan_schema_invalid", path, error.message)


def _fail(code: str, path: str, message: str = "") -> None:
    raise HipFgmresCheckpointHistoryPlanV1Error(code, path, message)


__all__ = [
    "HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_BLOCK_SIZE_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_MAGIC_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_CAPABILITY_PROFILE_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_PLAN_SCHEMA_VERSION_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_SOLUTION_ROLE_CODE_V1",
    "HIP_FGMRES_CHECKPOINT_HISTORY_TRUE_RESIDUAL_ROLE_CODE_V1",
    "HipFgmresCheckpointHistoryBlobV1",
    "HipFgmresCheckpointHistoryBufferPlanV1",
    "HipFgmresCheckpointHistoryPlanV1",
    "HipFgmresCheckpointHistoryPlanV1Error",
    "HipFgmresCheckpointHistoryRestartRowV1",
    "compile_hip_fgmres_checkpoint_history_plan_v1",
    "decode_hip_fgmres_checkpoint_history_blob_v1",
    "hip_fgmres_checkpoint_history_blob_abi_payload_v1",
    "validate_hip_fgmres_checkpoint_history_blob_pair_v1",
    "validate_hip_fgmres_checkpoint_history_plan_v1",
]
