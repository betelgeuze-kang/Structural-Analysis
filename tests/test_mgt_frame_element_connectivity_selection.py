"""Contract tests for authoritative MGT frame-element connectivity binding."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys

import numpy as np
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
PHASE1 = REPO_ROOT / "implementation" / "phase1"
sys.path.insert(0, str(PHASE1))

from run_mgt_coupled_frame_surface_sparse_equilibrium import (  # noqa: E402
    _select_frame_elements,
)


def _select(
    *,
    node_xyz: np.ndarray,
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    elem_id: np.ndarray,
    elem_type_code: np.ndarray,
):
    n_elem = int(elem_id.shape[0])
    return _select_frame_elements(
        node_xyz=node_xyz,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=np.arange(100, 100 + n_elem, dtype=np.int32),
        elem_material_id=np.arange(200, 200 + n_elem, dtype=np.int32),
    )


def test_frame_element_rows_bind_to_their_own_csr_connectivity() -> None:
    node_xyz = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 3.0, 0.0],
            [0.0, 0.0, 4.0],
        ]
    )
    elements, metadata = _select(
        node_xyz=node_xyz,
        conn_ptr=np.asarray([0, 3, 5, 7]),
        conn_idx=np.asarray([0, 1, 2, 2, 3, 0, 1]),
        elem_id=np.asarray([10, 20, 30]),
        elem_type_code=np.asarray([2, 1, 1]),
    )

    assert [(element.elem_id, element.node_i, element.node_j) for element in elements] == [
        (20, 2, 3),
        (30, 0, 1),
    ]
    assert [element.length_m for element in elements] == [5.0, 10.0]
    assert metadata["frame_connectivity_source"] == "elem_conn_ptr/elem_conn_idx"
    assert metadata["edge_index_used_for_element_binding"] is False
    assert metadata["line_element_row_accounting_exact"] is True
    assert "edge_index" not in inspect.signature(_select_frame_elements).parameters


def test_invalid_line_connectivity_is_skipped_with_exact_diagnostics() -> None:
    elements, metadata = _select(
        node_xyz=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [0.1, 0.0, 0.0],
                [1.0, 0.0, 0.0],
            ]
        ),
        conn_ptr=np.asarray([0, 3, 5, 7, 9]),
        conn_idx=np.asarray([0, 1, 2, 0, 9, 1, 1, 0, 1]),
        elem_id=np.asarray([101, 102, 103, 104]),
        elem_type_code=np.ones(4, dtype=np.int32),
    )

    assert elements == []
    assert metadata["raw_line_element_count"] == 4
    assert metadata["skipped_invalid_line_connectivity_count"] == 3
    assert metadata["invalid_line_connectivity_element_id_head"] == [101, 102, 103]
    assert metadata["skipped_short_or_degenerate_line_count"] == 1
    assert metadata["line_element_row_accounting_exact"] is True


@pytest.mark.parametrize(
    ("conn_ptr", "conn_idx", "message"),
    [
        (np.asarray([0, 2]), np.asarray([0, 1, 1, 2]), "exactly"),
        (np.asarray([0, 3, 2]), np.asarray([0, 1]), "monotonic"),
        (np.asarray([1, 2, 4]), np.asarray([0, 1, 1, 2]), "span conn_idx"),
    ],
)
def test_malformed_connectivity_contract_fails_closed(
    conn_ptr: np.ndarray,
    conn_idx: np.ndarray,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _select(
            node_xyz=np.asarray(
                [
                    [0.0, 0.0, 0.0],
                    [1.0, 0.0, 0.0],
                    [2.0, 0.0, 0.0],
                ]
            ),
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            elem_id=np.asarray([11, 12]),
            elem_type_code=np.ones(2, dtype=np.int32),
        )


def test_real_mgt_element_1224_uses_its_authoritative_connectivity_row() -> None:
    roundtrip_npz = (
        PHASE1
        / "open_data"
        / "midas"
        / "midas_generator_33.optimized.roundtrip.npz"
    )
    with np.load(roundtrip_npz, allow_pickle=False) as archive:
        node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
        conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
        conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)
        elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
        elem_type_code = np.asarray(archive["elem_type_code"], dtype=np.int32)
        elem_section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
        elem_material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)

    elements, metadata = _select_frame_elements(
        node_xyz=node_xyz,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
    )
    row = int(np.flatnonzero(elem_id == 1224)[0])
    expected = tuple(int(value) for value in conn_idx[conn_ptr[row] : conn_ptr[row + 1]])
    actual = next(element for element in elements if element.elem_id == 1224)

    assert expected == (2273, 2274)
    assert (actual.node_i, actual.node_j) == expected
    assert metadata["skipped_invalid_line_connectivity_count"] == 0
    assert metadata["line_element_row_accounting_exact"] is True
