from __future__ import annotations

from dataclasses import replace
import struct

import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend.fgmres_checkpoint_history_plan_v1 import (
    HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1,
    HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1,
    HIP_FGMRES_CHECKPOINT_HISTORY_MAGIC_V1,
    HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1,
    HipFgmresCheckpointHistoryPlanV1Error,
    compile_hip_fgmres_checkpoint_history_plan_v1,
    decode_hip_fgmres_checkpoint_history_blob_v1,
    hip_fgmres_checkpoint_history_blob_abi_payload_v1,
    validate_hip_fgmres_checkpoint_history_blob_pair_v1,
    validate_hip_fgmres_checkpoint_history_plan_v1,
)


def _blob(
    *,
    role_code: int,
    free_dof_count: int = 3,
    restart_count: int = 2,
    capture_count: int = 4,
    rows: tuple[tuple[int, ...], ...] = (
        (1, 1, 1, 2, 1, 0, 0, 0),
        (1, 2, 0, 3, 5, 2, 10, 0),
    ),
    error_bits: int = 0,
) -> bytes:
    plan = compile_hip_fgmres_checkpoint_history_plan_v1(
        free_dof_count,
        restart_count,
    )
    payload = bytearray(plan.blob_byte_count)
    vector_bytes = 8 * free_dof_count * restart_count
    struct.pack_into(
        "<16i",
        payload,
        0,
        HIP_FGMRES_CHECKPOINT_HISTORY_MAGIC_V1,
        HIP_FGMRES_CHECKPOINT_HISTORY_BLOB_ABI_VERSION_V1,
        role_code,
        1,
        free_dof_count,
        restart_count,
        HIP_FGMRES_CHECKPOINT_HISTORY_HEADER_BYTES_V1,
        HIP_FGMRES_CHECKPOINT_HISTORY_RESTART_BYTES_V1,
        plan.payload_offset_bytes,
        vector_bytes,
        0,
        capture_count,
        sum(row[0] for row in rows),
        error_bits,
        0,
        0,
    )
    for index, row in enumerate(rows):
        struct.pack_into(
            "<8i",
            payload,
            plan.header_bytes + index * plan.restart_bytes,
            *row,
        )
    values = np.arange(1, free_dof_count * restart_count + 1, dtype="<f8")
    payload[plan.payload_offset_bytes :] = values.tobytes()
    return bytes(payload)


def test_checkpoint_history_plan_has_two_additive_blob_extents() -> None:
    plan = compile_hip_fgmres_checkpoint_history_plan_v1(24, 3)
    assert validate_hip_fgmres_checkpoint_history_plan_v1(plan) is plan
    assert plan.payload_offset_bytes == 64 + 32 * 3
    assert plan.payload_byte_count == 8 * 24 * 3
    assert plan.blob_byte_count == 736
    assert plan.owned_device_byte_length == 1472
    assert tuple(row.role for row in plan.buffers) == (
        "checkpoint_solution_history",
        "checkpoint_true_residual_history",
    )
    assert all(row.payload_shape == (3, 24) for row in plan.buffers)
    assert plan.plan_hash == plan.to_dict()["plan_hash"]


def test_checkpoint_history_abi_layout_is_fixed_and_little_endian() -> None:
    abi = hip_fgmres_checkpoint_history_blob_abi_payload_v1()
    assert abi["header_bytes"] == 64
    assert abi["restart_bytes"] == 32
    assert abi["header_layout"] == "16*i32"
    assert abi["restart_layout"] == "8*i32"
    assert abi["payload"]["blob_byte_formula"] == "64+32*R+8*R*F"
    assert abi["publication"]["row_marker_order"].startswith("threadfence")


@pytest.mark.parametrize(
    ("free_dof_count", "restart_count"),
    ((0, 1), (1, 0), (-1, 1), (1, 4097), (True, 1)),
)
def test_checkpoint_history_plan_rejects_invalid_dimensions(
    free_dof_count: int,
    restart_count: int,
) -> None:
    with pytest.raises(
        HipFgmresCheckpointHistoryPlanV1Error,
        match="hip_fgmres_checkpoint_history_dimension_invalid",
    ):
        compile_hip_fgmres_checkpoint_history_plan_v1(
            free_dof_count,
            restart_count,
        )


def test_checkpoint_history_plan_rejects_coherent_field_mutation() -> None:
    plan = compile_hip_fgmres_checkpoint_history_plan_v1(4, 2)
    with pytest.raises(HipFgmresCheckpointHistoryPlanV1Error):
        validate_hip_fgmres_checkpoint_history_plan_v1(
            replace(plan, blob_byte_count=plan.blob_byte_count + 8)
        )
    with pytest.raises(HipFgmresCheckpointHistoryPlanV1Error):
        validate_hip_fgmres_checkpoint_history_plan_v1(
            replace(plan, plan_hash="sha256:" + "0" * 64)
        )


def test_checkpoint_history_blob_pair_decodes_rows_and_vectors() -> None:
    solution_payload = _blob(role_code=1)
    residual_payload = _blob(role_code=2)
    solution, residual = validate_hip_fgmres_checkpoint_history_blob_pair_v1(
        solution_payload,
        residual_payload,
        expected_free_dof_count=3,
        expected_maximum_restart_count=2,
        expected_capture_launch_count=4,
    )
    assert solution.capture_launch_count == 4
    assert solution.populated_restart_count == 2
    assert solution.restart_rows[1].end_iteration == 3
    assert solution.vector_array.shape == (2, 3)
    assert np.array_equal(solution.vector_array, residual.vector_array)
    assert not solution.vector_array.flags.writeable


def test_checkpoint_history_blob_rejects_device_error_and_dirty_unpublished_row() -> (
    None
):
    with pytest.raises(
        HipFgmresCheckpointHistoryPlanV1Error,
        match="blob_header_invalid",
    ):
        decode_hip_fgmres_checkpoint_history_blob_v1(
            _blob(role_code=1, error_bits=1),
            expected_role="checkpoint_solution_history",
            expected_free_dof_count=3,
            expected_maximum_restart_count=2,
        )
    dirty = (
        (1, 1, 1, 2, 1, 0, 0, 0),
        (0, 2, 0, 0, 0, 0, 0, 0),
    )
    with pytest.raises(
        HipFgmresCheckpointHistoryPlanV1Error,
        match="unpublished_row_dirty",
    ):
        decode_hip_fgmres_checkpoint_history_blob_v1(
            _blob(role_code=1, rows=dirty),
            expected_role="checkpoint_solution_history",
            expected_free_dof_count=3,
            expected_maximum_restart_count=2,
        )


def test_checkpoint_history_blob_pair_rejects_metadata_splice() -> None:
    solution_payload = _blob(role_code=1)
    residual_rows = (
        (1, 1, 0, 1, 1, 0, 0, 0),
        (1, 2, 0, 3, 5, 2, 10, 0),
    )
    with pytest.raises(
        HipFgmresCheckpointHistoryPlanV1Error,
        match="blob_pair_mismatch",
    ):
        validate_hip_fgmres_checkpoint_history_blob_pair_v1(
            solution_payload,
            _blob(role_code=2, rows=residual_rows),
            expected_free_dof_count=3,
            expected_maximum_restart_count=2,
        )
