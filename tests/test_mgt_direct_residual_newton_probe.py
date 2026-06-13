from __future__ import annotations

import sys
import subprocess
from pathlib import Path

import numpy as np
from scipy.sparse import diags


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    _active_free,
    _expand_support_to_node_blocks,
    _load_checkpoint,
    _parse_matrix_free_basis_sources,
    _select_residual_element_block_rows,
    _select_residual_node_block_rows,
    _skipped_output_final_checkpoint_meta,
    _truncated_svd_lstsq,
    _unique_positive_alphas,
    parse_args,
)


def test_active_free_excludes_restrained_dofs() -> None:
    stiffness = diags([0.0, 2.0, 3.0, 0.0, 5.0], format="csr")

    active, free = _active_free(stiffness, restrained={2})

    np.testing.assert_array_equal(active, np.asarray([1, 2, 4], dtype=np.int64))
    np.testing.assert_array_equal(free, np.asarray([1, 4], dtype=np.int64))


def test_unique_positive_alphas_clamps_and_deduplicates() -> None:
    rows = _unique_positive_alphas(
        [
            ("configured", 0.5),
            ("l2", 0.50000000000000001),
            ("too_small", 0.01),
            ("too_large", 2.0),
            ("negative", -1.0),
        ],
        min_alpha=0.1,
        max_alpha=1.0,
    )

    assert rows == [
        ("configured", 0.5),
        ("too_small", 0.1),
        ("too_large", 1.0),
    ]


def test_parse_matrix_free_basis_sources_normalizes_aliases() -> None:
    assert _parse_matrix_free_basis_sources("") == ("history",)
    assert _parse_matrix_free_basis_sources("history,newton,current_newton") == (
        "history",
        "current_newton",
    )


def test_direct_residual_parser_exposes_residual_row_fastpath_flag() -> None:
    default_args = parse_args([])
    assert default_args.current_tangent_residual_row_use_residual_only_assembly is False
    assert default_args.current_tangent_residual_row_allow_negative_alphas is False

    enabled_args = parse_args(
        [
            "--current-tangent-residual-row-use-residual-only-assembly",
            "--current-tangent-residual-row-allow-negative-alphas",
        ]
    )
    assert enabled_args.current_tangent_residual_row_use_residual_only_assembly is True
    assert enabled_args.current_tangent_residual_row_allow_negative_alphas is True


def test_truncated_svd_lstsq_drops_ill_conditioned_direction() -> None:
    matrix = np.asarray([[1.0, 0.0], [0.0, 1.0e-12]], dtype=np.float64)
    rhs = np.asarray([2.0, 1.0], dtype=np.float64)

    coeffs, residual_sum, rank, singular_values, meta = _truncated_svd_lstsq(
        matrix,
        rhs,
        max_condition=1.0e6,
    )

    np.testing.assert_allclose(coeffs, np.asarray([2.0, 0.0]), rtol=0.0, atol=1.0e-12)
    assert residual_sum[0] == 1.0
    assert rank == 1
    np.testing.assert_allclose(singular_values, np.asarray([1.0, 1.0e-12]))
    assert meta["svd_kept_singular_value_count"] == 1
    assert meta["svd_dropped_singular_value_count"] == 1


def test_expand_support_to_node_blocks_uses_free_dof_node_groups() -> None:
    current_free = np.asarray([0, 1, 2, 6, 8, 11, 12], dtype=np.int64)
    support_cols = np.asarray([4], dtype=np.int64)

    expanded = _expand_support_to_node_blocks(
        support_cols,
        current_free,
        dof_per_node=6,
    )

    np.testing.assert_array_equal(expanded, np.asarray([3, 4, 5], dtype=np.int64))


def test_select_residual_node_block_rows_targets_full_high_residual_nodes() -> None:
    current_free = np.asarray([0, 1, 2, 6, 7, 8, 12, 13], dtype=np.int64)
    residual = np.asarray([1.0, -2.0, 0.5, 10.0, -1.0, 2.0, 3.0, -4.0], dtype=np.float64)

    rows, meta = _select_residual_node_block_rows(
        residual,
        current_free,
        target_node_count=1,
        dof_per_node=6,
    )

    np.testing.assert_array_equal(rows, np.asarray([3, 4, 5], dtype=np.int64))
    assert meta["selected_nodes"] == [1]
    assert meta["selected_node_row_counts"] == [{"node": 1, "row_count": 3}]


def test_select_residual_element_block_rows_targets_connected_free_dofs() -> None:
    current_free = np.asarray([0, 1, 2, 6, 7, 8, 12, 13], dtype=np.int64)
    residual = np.asarray([1.0, -2.0, 0.5, 10.0, -1.0, 2.0, 3.0, -4.0], dtype=np.float64)
    conn_ptr = np.asarray([0, 2, 4, 6], dtype=np.int64)
    conn_idx = np.asarray([0, 2, 0, 1, 1, 2], dtype=np.int64)
    elem_id = np.asarray([101, 202, 303], dtype=np.int64)
    elem_type_code = np.asarray([1, 2, 2], dtype=np.int32)

    rows, meta = _select_residual_element_block_rows(
        residual,
        current_free,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        target_element_count=1,
        dof_per_node=6,
    )

    np.testing.assert_array_equal(rows, np.asarray([3, 4, 5, 6, 7], dtype=np.int64))
    assert meta["target_element_count"] == 1
    assert meta["selected_elements"][0]["element_id"] == 303
    assert meta["selected_elements"][0]["row_count"] == 5
    assert meta["candidate_element_type_counts"] == {"1": 1, "2": 2}
    assert meta["selected_element_type_counts"] == {"2": 1}


def test_select_residual_element_block_rows_can_restrict_to_frame_elements() -> None:
    current_free = np.asarray([0, 1, 2, 6, 7, 8, 12, 13], dtype=np.int64)
    residual = np.asarray([1.0, -2.0, 0.5, 10.0, -1.0, 2.0, 3.0, -4.0], dtype=np.float64)
    conn_ptr = np.asarray([0, 2, 4, 6], dtype=np.int64)
    conn_idx = np.asarray([0, 2, 0, 1, 1, 2], dtype=np.int64)
    elem_id = np.asarray([101, 202, 303], dtype=np.int64)
    elem_type_code = np.asarray([1, 2, 2], dtype=np.int32)

    rows, meta = _select_residual_element_block_rows(
        residual,
        current_free,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        target_element_count=1,
        allowed_element_type_codes={1},
        dof_per_node=6,
    )

    np.testing.assert_array_equal(rows, np.asarray([0, 1, 2, 6, 7], dtype=np.int64))
    assert meta["selected_elements"][0]["element_id"] == 101
    assert meta["candidate_element_type_counts"] == {"1": 1}
    assert meta["selected_element_type_counts"] == {"1": 1}
    assert meta["allowed_element_type_codes"] == [1]


def test_select_residual_element_block_rows_can_expand_shared_node_neighbors() -> None:
    current_free = np.asarray([0, 1, 6, 7, 12, 13, 18, 19], dtype=np.int64)
    residual = np.asarray([1.0, 1.0, 10.0, 1.0, 2.0, 2.0, 3.0, 3.0], dtype=np.float64)
    conn_ptr = np.asarray([0, 2, 4, 6], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 1, 2, 2, 3], dtype=np.int64)
    elem_id = np.asarray([10, 20, 30], dtype=np.int64)

    rows, meta = _select_residual_element_block_rows(
        residual,
        current_free,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        target_element_count=1,
        neighbor_depth=1,
        dof_per_node=6,
    )

    np.testing.assert_array_equal(rows, np.asarray([0, 1, 2, 3, 4, 5, 6, 7], dtype=np.int64))
    assert meta["seed_element_count"] == 1
    assert meta["neighbor_depth"] == 1
    assert meta["target_element_count"] == 3
    assert [row["element_id"] for row in meta["selected_elements"]] == [20, 10, 30]


def test_load_checkpoint_reads_optional_history(tmp_path: Path) -> None:
    checkpoint = tmp_path / "state.npz"
    state_history = np.asarray([[0.0, 1.0], [0.25, 1.25]], dtype=np.float64)
    residual_history = np.asarray([[4.0, -2.0], [1.0, -0.5]], dtype=np.float64)
    np.savez_compressed(
        checkpoint,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        load_scale=np.asarray(0.656, dtype=np.float64),
        displacement_u=state_history[-1],
        residual_inf_n=np.asarray(1.0, dtype=np.float64),
        accepted_state_history_u=state_history,
        accepted_residual_history=residual_history,
    )

    meta, u, loaded_state_history, loaded_residual_history = _load_checkpoint(checkpoint)

    assert meta["checkpoint_schema"] == "mgt-direct-residual-newton-state.v1"
    assert meta["accepted_state_history_count"] == 2
    assert meta["accepted_residual_history_count"] == 2
    np.testing.assert_array_equal(u, state_history[-1])
    np.testing.assert_array_equal(loaded_state_history, state_history)
    np.testing.assert_array_equal(loaded_residual_history, residual_history)


def test_skipped_output_final_checkpoint_meta_marks_no_descent(tmp_path: Path) -> None:
    output = tmp_path / "no_descent_state.npz"
    source = tmp_path / "source_state.npz"

    meta = _skipped_output_final_checkpoint_meta(
        output_final_checkpoint_npz=output,
        checkpoint_npz=source,
        final_direct_residual_inf=5662.74655057728,
        reason="no_residual_descent",
    )

    assert meta == {
        "written": False,
        "path": str(output),
        "reason": "no_residual_descent",
        "direct_residual_inf_n": 5662.74655057728,
        "source_checkpoint_path": str(source),
    }


def test_direct_residual_cli_requires_explicit_cpu_diagnostic_ack(tmp_path: Path) -> None:
    out = tmp_path / "mgt_direct_residual_newton_probe.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/run_mgt_direct_residual_newton_probe.py"),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 2
    assert "--allow-cpu-diagnostic" in proc.stderr
    assert "ROCm/HIP closure evidence" in proc.stderr
    assert not out.exists()
