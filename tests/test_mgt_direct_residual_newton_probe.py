from __future__ import annotations

import sys
import subprocess
import types
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.sparse import diags


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_direct_residual_newton_probe as direct_probe  # noqa: E402
from run_mgt_direct_residual_newton_probe import (  # noqa: E402
    _active_free,
    _component_breakdown,
    _cpu_acceptance_refresh_closure_blocked,
    _expand_support_to_node_blocks,
    _full_load_closure_gate,
    _g1_fallback_zero_audit,
    _g1_hip_residual_engine_contract,
    _load_checkpoint,
    _load_frontier_component_top_rows,
    _parse_matrix_free_basis_sources,
    _select_residual_element_block_rows,
    _select_residual_node_block_rows,
    _skipped_output_final_checkpoint_meta,
    _truncated_svd_lstsq,
    _torch_hip_gmres_once,
    _unique_positive_alphas,
    parse_args,
    run_mgt_direct_residual_newton_probe,
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


def test_full_load_closure_gate_rejects_sub_full_load_checkpoint() -> None:
    sub_full = _full_load_closure_gate(0.656)
    full = _full_load_closure_gate(1.0)

    assert sub_full["required"] is True
    assert sub_full["observed_load_scale"] == 0.656
    assert sub_full["passed"] is False
    assert "must not be promoted" in sub_full["claim_boundary"]
    assert full["passed"] is True


def test_direct_residual_parser_exposes_residual_row_fastpath_flag() -> None:
    default_args = parse_args([])
    assert default_args.current_tangent_residual_row_use_residual_only_assembly is False
    assert default_args.current_tangent_residual_row_require_hip_batch_replay is False
    assert default_args.current_tangent_residual_row_allow_negative_alphas is False
    assert default_args.matrix_free_global_krylov_difference_scheme == "forward"
    assert default_args.matrix_free_global_krylov_batch_replay_backend == "cpu"
    assert default_args.matrix_free_global_krylov_require_hip_batch_replay is False
    assert default_args.apply_shell_material_tangent is False
    assert default_args.allow_frozen_shell_material_tangent_hip_replay is False
    assert default_args.allow_state_dependent_shell_material_tangent_hip_replay is False
    assert default_args.current_tangent_residual_row_per_state_batch_replay is False
    assert default_args.compact_output_final_checkpoint is False
    assert default_args.matrix_free_global_krylov_full_assembly_trial_replay is False
    assert default_args.include_residual_component_breakdown is False
    assert default_args.residual_component_breakdown_top_count == 24

    enabled_args = parse_args(
        [
            "--apply-shell-material-tangent",
            "--compact-output-final-checkpoint",
            "--matrix-free-global-krylov-full-assembly-trial-replay",
            "--matrix-free-global-krylov-difference-scheme",
            "central",
            "--matrix-free-global-krylov-batch-replay-backend",
            "hip_full_residual_resident",
            "--matrix-free-global-krylov-require-hip-batch-replay",
            "--include-residual-component-breakdown",
            "--residual-component-breakdown-top-count",
            "7",
            "--current-tangent-residual-row-target-mode",
            "current_component_rows",
            "--current-tangent-residual-row-jacobian-mode",
            "finite_difference",
            "--current-tangent-residual-row-support-selection",
            "target_rows",
            "--current-tangent-residual-row-use-residual-only-assembly",
            "--current-tangent-residual-row-per-state-batch-replay",
            "--current-tangent-residual-row-batch-replay-backend",
            "hip_full_residual",
            "--current-tangent-residual-row-require-hip-batch-replay",
            "--current-tangent-residual-row-allow-negative-alphas",
            "--allow-frozen-shell-material-tangent-hip-replay",
            "--allow-state-dependent-shell-material-tangent-hip-replay",
        ]
    )
    assert enabled_args.apply_shell_material_tangent is True
    assert enabled_args.compact_output_final_checkpoint is True
    assert enabled_args.matrix_free_global_krylov_full_assembly_trial_replay is True
    assert enabled_args.matrix_free_global_krylov_difference_scheme == "central"
    assert (
        enabled_args.matrix_free_global_krylov_batch_replay_backend
        == "hip_full_residual_resident"
    )
    assert enabled_args.matrix_free_global_krylov_require_hip_batch_replay is True
    assert enabled_args.include_residual_component_breakdown is True
    assert enabled_args.residual_component_breakdown_top_count == 7
    assert enabled_args.current_tangent_residual_row_target_mode == "current_component_rows"
    assert enabled_args.current_tangent_residual_row_jacobian_mode == "finite_difference"
    assert enabled_args.current_tangent_residual_row_support_selection == "target_rows"
    assert enabled_args.current_tangent_residual_row_use_residual_only_assembly is True
    assert enabled_args.current_tangent_residual_row_per_state_batch_replay is True
    assert enabled_args.current_tangent_residual_row_batch_replay_backend == "hip_full_residual"
    assert enabled_args.current_tangent_residual_row_require_hip_batch_replay is True
    assert enabled_args.current_tangent_residual_row_allow_negative_alphas is True
    assert enabled_args.allow_frozen_shell_material_tangent_hip_replay is True
    assert enabled_args.allow_state_dependent_shell_material_tangent_hip_replay is True


def test_direct_residual_parser_rejects_hip_required_cpu_row_backend() -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--current-tangent-residual-row-require-hip-batch-replay"])

    assert exc_info.value.code == 2


def test_direct_residual_parser_rejects_hip_required_cpu_global_backend() -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--matrix-free-global-krylov-require-hip-batch-replay"])

    assert exc_info.value.code == 2


def test_component_breakdown_identifies_top_row_dominant_component() -> None:
    component_forces = {
        "frame": np.asarray([0.0, 5.0, 0.0, 0.0], dtype=np.float64),
        "shell_membrane": np.asarray([0.0, -1.0, 0.0, 3.0], dtype=np.float64),
    }
    free = np.asarray([1, 3], dtype=np.int64)
    residual = np.asarray([4.0, -2.0], dtype=np.float64)
    rhs = np.asarray([1.0, 5.0], dtype=np.float64)

    breakdown = _component_breakdown(
        component_forces=component_forces,
        free=free,
        residual=residual,
        rhs=rhs,
        top_count=1,
    )

    assert breakdown["component_inf_n"] == {
        "frame": 5.0,
        "shell_membrane": 3.0,
    }
    assert breakdown["top_row_dominant_component_counts"] == {"frame": 1}
    row = breakdown["top_rows"][0]
    assert row["free_row"] == 0
    assert row["global_dof"] == 1
    assert row["node_index"] == 0
    assert row["dof"] == "uy"
    assert row["dominant_component"] == "frame"
    assert row["internal_sum_n"] == 4.0


def test_load_frontier_component_top_rows_accepts_nested_direct_probe_receipt(
    tmp_path: Path,
) -> None:
    receipt = tmp_path / "probe.json"
    receipt.write_text(
        """
{
  "final_direct_residual": {
    "residual_component_breakdown": {
      "top_rows": [
        {
          "global_dof": "13",
          "node_index": 2,
          "dominant_component": "shell_membrane",
          "residual_n": "4.5"
        }
      ]
    }
  }
}
""".strip(),
        encoding="utf-8",
    )

    rows = _load_frontier_component_top_rows(receipt)

    assert rows == [
        {
            "global_dof": 13,
            "node_index": 2,
            "dominant_component": "shell_membrane",
            "residual_n": 4.5,
        }
    ]


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


def test_select_residual_element_block_rows_can_target_shell_normal_dofs() -> None:
    current_free = np.asarray(
        [
            0,
            1,
            2,
            6,
            7,
            8,
            12,
            13,
            14,
            18,
            19,
            20,
        ],
        dtype=np.int64,
    )
    residual = np.asarray(
        [0.1, 0.1, 1.0, 0.1, 0.1, 9.0, 0.1, 0.1, 2.0, 0.1, 0.1, 3.0],
        dtype=np.float64,
    )
    conn_ptr = np.asarray([0, 2, 6], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 1, 2, 3, 0], dtype=np.int64)
    elem_id = np.asarray([101, 202], dtype=np.int64)
    elem_type_code = np.asarray([1, 2], dtype=np.int32)

    rows, meta = _select_residual_element_block_rows(
        residual,
        current_free,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        target_element_count=1,
        allowed_element_type_codes={2},
        target_dof_indices={2},
        dof_per_node=6,
    )

    np.testing.assert_array_equal(rows, np.asarray([2, 5, 8, 11], dtype=np.int64))
    assert meta["selected_elements"][0]["element_id"] == 202
    assert meta["selected_elements"][0]["row_count"] == 4
    assert meta["candidate_element_type_counts"] == {"2": 1}
    assert meta["selected_element_type_counts"] == {"2": 1}
    assert meta["allowed_element_type_codes"] == [2]
    assert meta["target_dof_indices"] == [2]


def test_select_residual_element_block_rows_can_target_geometry_shell_normal_dofs() -> None:
    current_free = np.asarray(
        [
            0,
            1,
            2,
            6,
            7,
            8,
            12,
            13,
            14,
            18,
            19,
            20,
        ],
        dtype=np.int64,
    )
    residual = np.asarray(
        [9.0, 0.1, 4.0, 8.0, 0.1, 3.0, 7.0, 0.1, 2.0, 6.0, 0.1, 1.0],
        dtype=np.float64,
    )
    node_xyz = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 1.0, 1.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    conn_ptr = np.asarray([0, 4], dtype=np.int64)
    conn_idx = np.asarray([0, 1, 2, 3], dtype=np.int64)
    elem_id = np.asarray([202], dtype=np.int64)
    elem_type_code = np.asarray([2], dtype=np.int32)

    rows, meta = _select_residual_element_block_rows(
        residual,
        current_free,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        node_xyz=node_xyz,
        elem_id=elem_id,
        elem_type_code=elem_type_code,
        target_element_count=1,
        allowed_element_type_codes={2},
        target_dof_indices={0, 1, 2},
        target_shell_geometry_normal_translation_rows=True,
        shell_normal_participation_threshold=0.9,
        dof_per_node=6,
    )

    np.testing.assert_array_equal(rows, np.asarray([0, 3, 6, 9], dtype=np.int64))
    assert meta["selected_elements"][0]["element_id"] == 202
    assert meta["selected_elements"][0]["row_count"] == 4
    assert meta["target_dof_indices"] == [0, 1, 2]
    assert meta["target_shell_geometry_normal_translation_rows"] is True
    assert meta["shell_normal_participation_threshold"] == 0.9


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


def test_torch_hip_gmres_requires_available_hip_device(monkeypatch) -> None:
    fake_torch = types.SimpleNamespace(
        __version__="2.6.0+rocm6.1",
        version=types.SimpleNamespace(hip="6.1.40091"),
        cuda=types.SimpleNamespace(is_available=lambda: False),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    correction, info, meta = _torch_hip_gmres_once(
        lambda vector: vector,
        np.asarray([1.0, -2.0], dtype=np.float64),
        restart=2,
    )

    np.testing.assert_array_equal(correction, np.asarray([0.0, 0.0]))
    assert info == 1
    assert meta["linear_solver_backend"] == "torch_hip_gmres"
    assert meta["torch_rocm_version"] == "6.1.40091"
    assert meta["torch_hip_device_available"] is False
    assert meta["hip_krylov_solver_used"] is False
    assert meta["unavailable_reason"] == "torch_hip_device_unavailable"


def test_rocm_device_runtime_diagnostics_reports_missing_device_nodes(tmp_path: Path) -> None:
    payload = direct_probe._rocm_device_runtime_diagnostics(
        kfd_path=tmp_path / "missing-kfd",
        dri_path=tmp_path / "missing-dri",
    )

    assert payload["device_nodes"]["kfd"]["exists"] is False
    assert payload["device_nodes"]["dri"]["exists"] is False
    assert "dev_kfd_missing" in payload["runtime_blockers"]
    assert "dev_dri_missing" in payload["runtime_blockers"]
    assert "rocminfo" in payload["rocm_commands"]
    assert isinstance(payload["process_group_ids"], list)


def test_rocm_hip_runtime_preflight_keeps_device_node_blockers(
    monkeypatch,
) -> None:
    fake_torch = types.SimpleNamespace(
        __version__="2.6.0+rocm6.1",
        version=types.SimpleNamespace(hip="6.1.40091"),
        cuda=types.SimpleNamespace(is_available=lambda: False),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        direct_probe,
        "_rocm_device_runtime_diagnostics",
        lambda: {
            "device_nodes": {
                "kfd": {"path": "/dev/kfd", "exists": False},
                "dri": {"path": "/dev/dri", "exists": False},
            },
            "process_group_ids": [1000],
            "rocm_commands": {
                "rocminfo": "/usr/bin/rocminfo",
                "rocm_smi": "/usr/local/bin/rocm-smi",
                "hipcc": None,
            },
            "visibility_settings": {},
            "runtime_blockers": ["dev_kfd_missing", "dev_dri_missing"],
        },
    )

    payload = direct_probe._rocm_hip_runtime_preflight()

    assert payload["hip_available"] is False
    assert payload["torch_importable"] is True
    assert payload["torch_rocm_build"] is True
    assert payload["torch_hip_device_available"] is False
    assert payload["unavailable_reason"] == "torch_hip_device_unavailable"
    assert payload["runtime_blockers"] == ["dev_kfd_missing", "dev_dri_missing"]
    assert payload["device_nodes"]["kfd"]["exists"] is False
    assert payload["rocm_commands"]["rocminfo"] == "/usr/bin/rocminfo"


def test_cpu_acceptance_refresh_blocks_hip_required_closure() -> None:
    assert _cpu_acceptance_refresh_closure_blocked(
        {
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_backend": "cpu_full_assembly",
            "accepted_state_refresh_cpu_used": True,
        }
    )
    assert not _cpu_acceptance_refresh_closure_blocked(
        {
            "promoted_to_final_state": True,
            "require_hip_batch_replay": False,
            "accepted_state_refresh_backend": "cpu_full_assembly",
            "accepted_state_refresh_cpu_used": True,
        }
    )
    assert not _cpu_acceptance_refresh_closure_blocked(
        {
            "promoted_to_final_state": False,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_cpu_used": True,
        }
    )
    assert _cpu_acceptance_refresh_closure_blocked(
        {
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_cpu_used": False,
            "accepted_state_refresh_backend": "hip_full_residual_batch_replay",
            "accepted_state_tangent_refresh_backend": "cpu_full_assembly",
            "accepted_state_tangent_refresh_cpu_used": True,
        }
    )
    assert not _cpu_acceptance_refresh_closure_blocked(
        {
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_cpu_used": False,
            "accepted_state_refresh_backend": "hip_full_residual_batch_replay",
            "accepted_state_tangent_refresh_backend": (
                "not_refreshed_not_needed_after_global_krylov"
            ),
            "accepted_state_tangent_refresh_cpu_used": False,
        }
    )


def test_cpu_acceptance_refresh_gate_flag_covers_row_correction_component(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The gate-level ``cpu_acceptance_refresh_closure_blocked`` flag must be
    True when EITHER the matrix-free global Krylov OR the current-tangent
    residual-row correction promoted a HIP-required final state via CPU
    residual acceptance or CPU tangent refresh. A row-only CPU leak would
    otherwise leave the gate flag False while the audit-level
    ``fallback_zero_audit`` still records the boundary.
    """
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    real_check = direct_probe._cpu_acceptance_refresh_closure_blocked
    call_count = {"n": 0}

    def fake_check(component: dict[str, Any]) -> bool:
        call_count["n"] += 1
        is_row_correction = "per_state_batch_replay_enabled" in component
        if is_row_correction:
            return True
        return real_check(component)

    monkeypatch.setattr(
        direct_probe, "_cpu_acceptance_refresh_closure_blocked", fake_check
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    assert call_count["n"] == 2, (
        f"Expected _cpu_acceptance_refresh_closure_blocked to be called "
        f"exactly twice (global krylov + row correction), got {call_count['n']}"
    )
    gate = payload["gate_assessment"]
    assert gate["cpu_acceptance_refresh_closure_blocked"] is True
    assert "rocm_hip_acceptance_refresh_required_for_closure" in payload["blockers"]
    assert payload["direct_residual_newton_ready"] is False
    assert payload["gate_assessment"]["fallback_zero_passed"] is False


def test_cpu_acceptance_refresh_gate_flag_still_false_when_no_cpu_refresh(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Regression: the gate-level ``cpu_acceptance_refresh_closure_blocked``
    flag must remain False when neither component uses CPU acceptance or
    CPU tangent refresh.
    """
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    real_check = direct_probe._cpu_acceptance_refresh_closure_blocked

    def fake_check(component: dict[str, Any]) -> bool:
        return real_check(component)

    monkeypatch.setattr(
        direct_probe, "_cpu_acceptance_refresh_closure_blocked", fake_check
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    gate = payload["gate_assessment"]
    assert gate["cpu_acceptance_refresh_closure_blocked"] is False


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


def test_rocm_hip_preflight_blocks_when_device_nodes_fail_despite_torch_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_torch = types.SimpleNamespace(
        __version__="2.6.0+rocm6.1",
        version=types.SimpleNamespace(hip="6.1.40091"),
        cuda=types.SimpleNamespace(
            is_available=lambda: True,
            device_count=lambda: 1,
            get_device_name=lambda _index: "fixture-amd-gpu",
        ),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        direct_probe,
        "_rocm_device_runtime_diagnostics",
        lambda: {
            "device_nodes": {
                "kfd": {"path": "/dev/kfd", "exists": False},
                "dri": {"path": "/dev/dri", "exists": False},
            },
            "process_group_ids": [],
            "rocm_commands": {"rocminfo": None, "rocm_smi": None, "hipcc": None},
            "visibility_settings": {},
            "runtime_blockers": ["dev_kfd_missing", "dev_dri_missing"],
        },
    )

    payload = direct_probe._rocm_hip_runtime_preflight()

    assert payload["torch_importable"] is True
    assert payload["torch_rocm_build"] is True
    assert payload["torch_hip_device_available"] is True
    assert payload["hip_available"] is False
    assert payload["unavailable_reason"] == "rocm_device_runtime_blocked"
    assert payload["runtime_blockers"] == ["dev_kfd_missing", "dev_dri_missing"]
    assert "torch_hip_device_count" not in payload


def test_direct_residual_cli_allows_hip_required_without_cpu_diagnostic_ack(
    tmp_path: Path,
    monkeypatch,
) -> None:
    called: list[dict[str, Any]] = []
    out = tmp_path / "hip_required_probe.json"

    def mock_run(**kwargs: Any) -> dict[str, Any]:
        called.append(kwargs)
        return {
            "status": "partial",
            "base_direct_residual": {},
            "matrix_free_global_krylov": {},
        }

    monkeypatch.setattr(
        direct_probe,
        "run_mgt_direct_residual_newton_probe",
        mock_run,
    )

    exit_code = direct_probe.main(
        [
            "--mgt-path",
            str(tmp_path / "missing.mgt"),
            "--checkpoint-npz",
            str(tmp_path / "missing.npz"),
            "--output-json",
            str(out),
            "--enable-matrix-free-global-krylov",
            "--matrix-free-global-krylov-batch-replay-backend",
            "hip_full_residual_resident",
            "--matrix-free-global-krylov-require-hip-batch-replay",
        ]
    )

    assert exit_code == 0
    assert len(called) == 1
    assert called[0]["enable_matrix_free_global_krylov"] is True
    assert called[0]["matrix_free_global_krylov_require_hip_batch_replay"] is True
    assert (
        called[0]["matrix_free_global_krylov_batch_replay_backend"]
        == "hip_full_residual_resident"
    )
    assert not out.exists()


def test_direct_residual_cli_mixed_cpu_lane_still_requires_cpu_diagnostic_ack(
    tmp_path: Path,
) -> None:
    out = tmp_path / "mixed_probe.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "implementation/phase1/run_mgt_direct_residual_newton_probe.py"),
            "--mgt-path",
            str(tmp_path / "missing.mgt"),
            "--checkpoint-npz",
            str(tmp_path / "missing.npz"),
            "--output-json",
            str(out),
            "--enable-matrix-free-global-krylov",
            "--matrix-free-global-krylov-batch-replay-backend",
            "hip_full_residual_resident",
            "--matrix-free-global-krylov-require-hip-batch-replay",
            "--enable-current-tangent-residual-row-correction",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "--allow-cpu-diagnostic" in proc.stderr
    assert not out.exists()


def test_direct_residual_cli_hip_required_disabled_lane_requires_cpu_diagnostic_ack(
    tmp_path: Path,
) -> None:
    out = tmp_path / "disabled_hip_probe.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "implementation/phase1/run_mgt_direct_residual_newton_probe.py"),
            "--mgt-path",
            str(tmp_path / "missing.mgt"),
            "--checkpoint-npz",
            str(tmp_path / "missing.npz"),
            "--output-json",
            str(out),
            "--matrix-free-global-krylov-require-hip-batch-replay",
            "--matrix-free-global-krylov-batch-replay-backend",
            "hip_full_residual_resident",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "--allow-cpu-diagnostic" in proc.stderr
    assert not out.exists()


def test_direct_residual_cli_row_correction_hip_required_without_cpu_diagnostic_ack(
    tmp_path: Path,
    monkeypatch,
) -> None:
    called: list[dict[str, Any]] = []
    out = tmp_path / "row_hip_probe.json"

    def mock_run(**kwargs: Any) -> dict[str, Any]:
        called.append(kwargs)
        return {
            "status": "partial",
            "base_direct_residual": {},
            "matrix_free_global_krylov": {},
        }

    monkeypatch.setattr(
        direct_probe,
        "run_mgt_direct_residual_newton_probe",
        mock_run,
    )

    exit_code = direct_probe.main(
        [
            "--mgt-path",
            str(tmp_path / "missing.mgt"),
            "--checkpoint-npz",
            str(tmp_path / "missing.npz"),
            "--output-json",
            str(out),
            "--enable-current-tangent-residual-row-correction",
            "--current-tangent-residual-row-batch-replay-backend",
            "hip_full_residual_resident",
            "--current-tangent-residual-row-require-hip-batch-replay",
        ]
    )

    assert exit_code == 0
    assert len(called) == 1
    assert called[0]["enable_current_tangent_residual_row_correction"] is True
    assert called[0]["current_tangent_residual_row_require_hip_batch_replay"] is True
    assert (
        called[0]["current_tangent_residual_row_batch_replay_backend"]
        == "hip_full_residual_resident"
    )
    assert not out.exists()


def test_direct_residual_hip_required_preflight_stops_before_missing_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "hip_preflight_receipt.json"

    monkeypatch.setattr(
        direct_probe,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "2026-06-21T00:00:00+00:00",
            "hip_available": False,
            "torch_importable": True,
            "torch_rocm_build": True,
            "torch_rocm_version": "6.1.40091",
            "torch_hip_device_available": False,
            "unavailable_reason": "torch_hip_device_unavailable",
        },
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=tmp_path / "missing.mgt",
        checkpoint_npz=tmp_path / "missing.npz",
        output_json=output,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual_resident",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["blockers"] == payload["blockers"]
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["status"] == "partial"
    assert payload["direct_residual_newton_ready"] is False
    assert payload["rocm_hip_runtime_preflight"]["hip_available"] is False
    assert "rocm_hip_runtime_unavailable" in payload["blockers"]
    assert "g1_fallback_zero_audit_not_closed" in payload["blockers"]
    assert "mgt_missing" not in payload["blockers"]
    assert "checkpoint_missing" not in payload["blockers"]

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert global_krylov["attempted"] is False
    assert global_krylov["batch_replay_backend"] == "hip_full_residual_resident"
    assert global_krylov["require_hip_batch_replay"] is True
    assert global_krylov["linear_solver_backend"] == "torch_hip_gmres"
    assert (
        global_krylov["linear_solver_backend_auto_selected_reason"]
        == "hip_batch_replay_required_suppresses_host_gmres"
    )

    gate = payload["gate_assessment"]
    assert gate["material_newton_breadth_passed"] is False
    assert gate["material_newton_breadth_blockers"] == [
        "rocm_hip_runtime_unavailable",
        "material_newton_not_executed",
    ]
    assert gate["consistent_residual_jacobian_newton_passed"] is False
    assert gate["consistent_residual_jacobian_newton_blockers"] == [
        "rocm_hip_runtime_unavailable",
        "consistent_residual_jacobian_newton_not_executed",
    ]
    assert gate["fallback_zero_passed"] is False
    assert gate["fallback_zero_audit"]["fallback_zero_boundary_count"] == 1
    residual_contract = payload["residual_contract"]
    assert residual_contract["material_newton_gate_passed"] is False
    assert residual_contract["state_dependent_material_newton_closure_passed"] is False
    assert residual_contract["consistent_residual_jacobian_newton_gate_passed"] is False


def test_direct_residual_non_hip_missing_mgt_behavior_unchanged(tmp_path: Path) -> None:
    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=tmp_path / "missing.mgt",
        checkpoint_npz=tmp_path / "missing.npz",
    )

    assert payload == {
        "schema_version": "mgt-direct-residual-newton-probe.v1",
        "generated_at": payload["generated_at"],
        "status": "blocked",
        "blockers": ["mgt_missing"],
    }


def test_explicit_torch_hip_gmres_preflight_stops_before_missing_inputs_without_batch_replay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "gmres_only_preflight_receipt.json"

    monkeypatch.setattr(
        direct_probe,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "2026-06-21T00:00:00+00:00",
            "hip_available": False,
            "torch_importable": True,
            "torch_rocm_build": True,
            "torch_rocm_version": "6.1.40091",
            "torch_hip_device_available": False,
            "unavailable_reason": "torch_hip_device_unavailable",
        },
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=tmp_path / "missing.mgt",
        checkpoint_npz=tmp_path / "missing.npz",
        output_json=output,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_linear_solver_backend="torch_hip_gmres",
    )

    assert output.exists()
    assert payload["status"] == "partial"
    assert payload["direct_residual_newton_ready"] is False
    assert payload["rocm_hip_runtime_preflight"]["hip_available"] is False
    assert "rocm_hip_runtime_unavailable" in payload["blockers"]
    assert "g1_fallback_zero_audit_not_closed" in payload["blockers"]
    assert "mgt_missing" not in payload["blockers"]
    assert "checkpoint_missing" not in payload["blockers"]

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert global_krylov["attempted"] is False
    assert global_krylov["require_hip_batch_replay"] is False
    assert global_krylov["linear_solver_backend"] == "torch_hip_gmres"
    assert global_krylov["require_hip_krylov_solver"] is True
    assert global_krylov["stop_reason"] == "rocm_hip_runtime_unavailable"

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is False
    assert row_correction["attempted"] is False

    gate = payload["gate_assessment"]
    assert gate["fallback_zero_passed"] is False
    assert gate["fallback_zero_audit"]["fallback_zero_boundary_count"] == 1


def test_direct_residual_row_correction_hip_preflight_stops_before_missing_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output = tmp_path / "row_hip_preflight_receipt.json"

    monkeypatch.setattr(
        direct_probe,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "2026-06-21T00:00:00+00:00",
            "hip_available": False,
            "torch_importable": True,
            "torch_rocm_build": True,
            "torch_rocm_version": "6.1.40091",
            "torch_hip_device_available": False,
            "unavailable_reason": "torch_hip_device_unavailable",
        },
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=tmp_path / "missing.mgt",
        checkpoint_npz=tmp_path / "missing.npz",
        output_json=output,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
    )

    assert output.exists()
    assert payload["status"] == "partial"
    assert payload["direct_residual_newton_ready"] is False
    assert payload["rocm_hip_runtime_preflight"]["hip_available"] is False
    assert "rocm_hip_runtime_unavailable" in payload["blockers"]
    assert "g1_fallback_zero_audit_not_closed" in payload["blockers"]
    assert "mgt_missing" not in payload["blockers"]
    assert "checkpoint_missing" not in payload["blockers"]

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is False
    assert global_krylov["attempted"] is False

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["attempted"] is False
    assert row_correction["batch_replay_backend"] == "hip_full_residual"
    assert row_correction["require_hip_batch_replay"] is True
    assert row_correction["stop_reason"] == "rocm_hip_runtime_unavailable"

    gate = payload["gate_assessment"]
    assert gate["fallback_zero_passed"] is False
    assert gate["fallback_zero_audit"]["fallback_zero_boundary_count"] == 1


def test_g1_fallback_zero_audit_passes_when_no_hip_required_paths() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": False,
            "require_hip_krylov_solver": False,
            "host_krylov_solver_used": True,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": False,
        },
    )

    assert audit["fallback_zero_passed"] is True
    assert audit["fallback_zero_boundary_count"] == 0
    assert audit["fallback_zero_boundaries"] == []


def test_g1_hip_residual_engine_contract_passes_for_hip_required_global_path() -> None:
    contract = _g1_hip_residual_engine_contract(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "batch_replay_backend": "hip_full_residual_resident",
            "require_hip_batch_replay": True,
            "require_hip_krylov_solver": True,
            "hip_krylov_solver_used": True,
            "host_krylov_solver_used": False,
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    assert contract["hip_residual_engine_contract_passed"] is True
    assert contract["hip_residual_engine_required_lane_count"] == 1
    assert contract["hip_residual_engine_passed_lane_count"] == 1
    assert contract["hip_residual_engine_backends"] == ["hip_full_residual_resident"]
    assert contract["hip_residual_engine_blockers"] == []


def test_g1_hip_residual_engine_contract_blocks_host_or_missing_engine() -> None:
    contract = _g1_hip_residual_engine_contract(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "batch_replay_backend": "cpu",
            "require_hip_batch_replay": True,
            "require_hip_krylov_solver": True,
            "host_krylov_solver_used": True,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "batch_replay_backend": "hip_full_residual",
            "require_hip_batch_replay": True,
            "cpu_batch_replay_fallback_suppressed": True,
        },
    )

    assert contract["hip_residual_engine_contract_passed"] is False
    assert contract["hip_residual_engine_required_lane_count"] == 2
    blockers = set(contract["hip_residual_engine_blockers"])
    assert "matrix_free_global_krylov::residual_replay_backend_not_hip" in blockers
    assert "matrix_free_global_krylov::host_krylov_solver_used" in blockers
    assert "current_tangent_residual_row_correction::cpu_batch_replay_fallback_suppressed" in blockers


def test_g1_fallback_zero_audit_passes_when_not_attempted_or_not_enabled() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": True,
            "host_krylov_solver_used": True,
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": True,
            "hip_batch_replay_required_unavailable": True,
        },
    )

    assert audit["fallback_zero_passed"] is True
    assert audit["fallback_zero_boundary_count"] == 0


def test_g1_fallback_zero_audit_fails_global_krylov_host_gmres() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "require_hip_krylov_solver": False,
            "host_krylov_solver_used": True,
            "accepted_state_refresh_backend": "hip_full_residual",
            "accepted_state_refresh_hip_used": True,
            "accepted_state_refresh_cpu_used": False,
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "global_krylov_host_gmres_used_with_hip_required" in boundaries


def test_g1_fallback_zero_audit_fails_global_krylov_hip_replay_unavailable() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": True,
            "hip_batch_replay_required_unavailable": True,
            "hip_batch_replay_required_unavailable_reason": "hip_backend_prepare_failed",
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    assert audit["fallback_zero_passed"] is False
    assert audit["fallback_zero_boundary_count"] >= 1
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "global_krylov_hip_replay_required_unavailable" in boundaries


def test_g1_fallback_zero_audit_fails_promoted_global_without_hip_refresh() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_backend": "cpu_full_assembly",
            "accepted_state_refresh_cpu_used": False,
            "accepted_state_refresh_hip_used": False,
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert audit["fallback_zero_passed"] is False
    assert "global_krylov_hip_required_residual_refresh_missing" in boundaries


def test_g1_fallback_zero_audit_fails_promoted_row_without_hip_refresh() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_backend": "",
            "accepted_state_refresh_cpu_used": False,
            "accepted_state_refresh_hip_used": False,
            "accepted_state_tangent_refresh_backend": "hip_finite_difference_residual_jvp",
            "accepted_state_tangent_refresh_hip_used": True,
            "accepted_state_tangent_refresh_cpu_used": False,
        },
    )

    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert audit["fallback_zero_passed"] is False
    assert "row_correction_hip_required_residual_refresh_missing" in boundaries


def test_g1_fallback_zero_audit_fails_global_krylov_hip_krylov_solver_unavailable() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_krylov_solver": True,
            "hip_krylov_solver_required_unavailable": True,
            "hip_krylov_solver_required_unavailable_reason": "torch_hip_device_unavailable",
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "global_krylov_hip_krylov_solver_required_unavailable" in boundaries


def test_g1_fallback_zero_audit_fails_global_krylov_cpu_refresh_used() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_cpu_used": True,
            "accepted_state_tangent_refresh_cpu_used": True,
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "global_krylov_cpu_residual_acceptance_refresh_used" in boundaries
    assert "global_krylov_cpu_tangent_refresh_used" in boundaries


def test_g1_fallback_zero_audit_fails_global_krylov_missing_tangent_refresh() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_hip_used": True,
            "accepted_state_tangent_refresh_backend": "not_refreshed_not_needed_after_global_krylov",
            "accepted_state_tangent_refresh_cpu_used": False,
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "global_krylov_hip_required_tangent_refresh_missing" in boundaries


def test_g1_fallback_zero_audit_accepts_global_defer_closed_by_row_hip_fd_refresh() -> None:
    global_krylov = {
        "enabled": True,
        "attempted": True,
        "promoted_to_final_state": True,
        "batch_replay_backend": "hip_full_residual",
        "require_hip_batch_replay": True,
        "accepted_state_refresh_backend": "hip_full_residual",
        "accepted_state_refresh_hip_used": True,
        "accepted_state_refresh_cpu_used": False,
        "accepted_state_tangent_refresh_backend": (
            direct_probe.GLOBAL_TANGENT_REFRESH_DEFERRED_BACKEND
        ),
        "accepted_state_tangent_refresh_deferred_to": (
            direct_probe.GLOBAL_TANGENT_REFRESH_DEFERRED_TO_ROW
        ),
        "accepted_state_tangent_refresh_closure_blocked": True,
        "accepted_state_tangent_refresh_closure_blocker": (
            direct_probe.GLOBAL_TANGENT_REFRESH_DEFERRED_BLOCKER
        ),
        "accepted_state_tangent_refresh_cpu_used": False,
    }
    row_correction = {
        "enabled": True,
        "attempted": True,
        "promoted_to_final_state": True,
        "batch_replay_backend": "hip_full_residual",
        "require_hip_batch_replay": True,
        "accepted_state_refresh_backend": "hip_full_residual",
        "accepted_state_refresh_hip_used": True,
        "accepted_state_refresh_cpu_used": False,
        "accepted_state_tangent_refresh_backend": "hip_finite_difference_residual_jvp",
        "accepted_state_tangent_refresh_hip_used": True,
        "accepted_state_tangent_refresh_cpu_used": False,
    }

    audit = _g1_fallback_zero_audit(global_krylov, row_correction)
    contract = _g1_hip_residual_engine_contract(global_krylov, row_correction)

    assert audit["fallback_zero_passed"] is True
    assert contract["hip_residual_engine_contract_passed"] is True
    assert contract["hip_residual_engine_blockers"] == []


def test_g1_fallback_zero_audit_blocks_global_defer_without_row_hip_fd_refresh() -> None:
    global_krylov = {
        "enabled": True,
        "attempted": True,
        "promoted_to_final_state": True,
        "batch_replay_backend": "hip_full_residual",
        "require_hip_batch_replay": True,
        "accepted_state_refresh_backend": "hip_full_residual",
        "accepted_state_refresh_hip_used": True,
        "accepted_state_refresh_cpu_used": False,
        "accepted_state_tangent_refresh_backend": (
            direct_probe.GLOBAL_TANGENT_REFRESH_DEFERRED_BACKEND
        ),
        "accepted_state_tangent_refresh_deferred_to": (
            direct_probe.GLOBAL_TANGENT_REFRESH_DEFERRED_TO_ROW
        ),
        "accepted_state_tangent_refresh_deferred_reason": "fixture_defer",
        "accepted_state_tangent_refresh_cpu_used": False,
    }
    row_correction = {
        "enabled": True,
        "attempted": False,
        "promoted_to_final_state": False,
        "batch_replay_backend": "hip_full_residual",
        "require_hip_batch_replay": True,
    }

    audit = _g1_fallback_zero_audit(global_krylov, row_correction)
    contract = _g1_hip_residual_engine_contract(global_krylov, row_correction)

    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert audit["fallback_zero_passed"] is False
    assert "global_krylov_hip_required_tangent_refresh_missing" in boundaries
    assert (
        "matrix_free_global_krylov::accepted_state_tangent_refresh_not_hip"
        in contract["hip_residual_engine_blockers"]
    )


def test_g1_fallback_zero_audit_fails_global_krylov_cpu_fallback_suppressed() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": True,
            "cpu_batch_replay_fallback_suppressed": True,
        },
        row_correction={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "global_krylov_cpu_batch_replay_fallback_suppressed" in boundaries


def test_g1_fallback_zero_audit_fails_row_correction_hip_replay_unavailable() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "hip_batch_replay_required_unavailable": True,
            "hip_batch_replay_required_unavailable_reason": "hip_backend_evaluate_failed",
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "row_correction_hip_replay_required_unavailable" in boundaries


def test_g1_fallback_zero_audit_fails_row_correction_cpu_fallback_suppressed() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "cpu_batch_replay_fallback_suppressed": True,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "row_correction_cpu_batch_replay_fallback_suppressed" in boundaries


def test_g1_fallback_zero_audit_fails_row_correction_cpu_refresh_used() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_cpu_used": True,
            "accepted_state_tangent_refresh_cpu_used": True,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "row_correction_cpu_residual_acceptance_refresh_used" in boundaries
    assert "row_correction_cpu_tangent_refresh_used" in boundaries


def test_g1_fallback_zero_audit_fails_row_correction_frozen_tangent_refresh() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "accepted_state_refresh_hip_used": True,
            "accepted_state_tangent_refresh_backend": (
                "frozen_previous_support_graph_fd_residual_jvp"
            ),
            "accepted_state_tangent_refresh_cpu_used": False,
            "frozen_support_graph_after_hip_residual_promotion": True,
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "row_correction_hip_required_tangent_refresh_missing" in boundaries


def test_g1_fallback_zero_audit_fails_row_correction_per_state_non_hip_trial() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": False,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": False,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": True,
            "per_state_batch_replay_enabled": True,
            "passes": [
                {
                    "trial_rows": [
                        {
                            "per_state_batch_replay": True,
                            "hip_full_residual_batch_replay": False,
                            "residual_batch_backend": "cpu",
                        }
                    ]
                }
            ],
        },
    )

    assert audit["fallback_zero_passed"] is False
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "row_correction_per_state_replay_non_hip_trial" in boundaries


def test_g1_fallback_zero_audit_aggregates_multiple_boundaries() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "host_krylov_solver_used": True,
            "hip_batch_replay_required_unavailable": True,
            "accepted_state_refresh_cpu_used": True,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": True,
            "hip_batch_replay_required_unavailable": True,
        },
    )

    assert audit["fallback_zero_passed"] is False
    assert audit["fallback_zero_boundary_count"] >= 4
    boundaries = {b["boundary"] for b in audit["fallback_zero_boundaries"]}
    assert "global_krylov_host_gmres_used_with_hip_required" in boundaries
    assert "global_krylov_hip_replay_required_unavailable" in boundaries
    assert "global_krylov_cpu_residual_acceptance_refresh_used" in boundaries
    assert "row_correction_hip_replay_required_unavailable" in boundaries


def test_python_api_rejects_hip_required_global_cpu_backend() -> None:
    with pytest.raises(ValueError, match="matrix_free_global_krylov_require_hip_batch_replay"):
        run_mgt_direct_residual_newton_probe(
            enable_matrix_free_global_krylov=True,
            matrix_free_global_krylov_batch_replay_backend="cpu",
            matrix_free_global_krylov_require_hip_batch_replay=True,
        )


def test_python_api_rejects_hip_required_row_cpu_backend() -> None:
    with pytest.raises(ValueError, match="current_tangent_residual_row_require_hip_batch_replay"):
        run_mgt_direct_residual_newton_probe(
            enable_current_tangent_residual_row_correction=True,
            current_tangent_residual_row_batch_replay_backend="cpu",
            current_tangent_residual_row_require_hip_batch_replay=True,
        )


def test_g1_fallback_zero_audit_only_triggered_when_hip_required() -> None:
    audit = _g1_fallback_zero_audit(
        global_krylov={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": False,
            "require_hip_krylov_solver": False,
            "host_krylov_solver_used": True,
            "accepted_state_refresh_cpu_used": True,
            "accepted_state_tangent_refresh_cpu_used": True,
        },
        row_correction={
            "enabled": True,
            "attempted": True,
            "promoted_to_final_state": True,
            "require_hip_batch_replay": False,
            "hip_batch_replay_required_unavailable": True,
            "cpu_batch_replay_fallback_suppressed": True,
        },
    )

    assert audit["fallback_zero_passed"] is True
    assert audit["fallback_zero_boundary_count"] == 0


FIXTURE_MGT = REPO_ROOT / "tests/fixtures/foundation_realish/foundation_deep_small.mgt"


def _make_checkpoint_npz(path: Path, *, dof_count: int, load_scale: float = 0.656) -> None:
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        load_scale=np.asarray(load_scale, dtype=np.float64),
        displacement_u=np.zeros(dof_count, dtype=np.float64),
        residual_inf_n=np.asarray(1.0, dtype=np.float64),
    )


def _mock_hip_preflight_available() -> dict[str, Any]:
    return {
        "checked_at": "2026-06-21T00:00:00+00:00",
        "hip_available": True,
        "torch_importable": True,
        "torch_rocm_build": True,
        "torch_rocm_version": "6.1.40091",
        "torch_hip_device_available": True,
        "torch_hip_device_count": 1,
        "torch_hip_device_name": "AMD Instinct MI300X",
    }


def _mock_hip_preflight_unavailable() -> dict[str, Any]:
    return {
        "checked_at": "2026-06-21T00:00:00+00:00",
        "hip_available": False,
        "torch_importable": True,
        "torch_rocm_build": True,
        "torch_rocm_version": "6.1.40091",
        "torch_hip_device_available": False,
        "unavailable_reason": "torch_hip_device_unavailable",
    }


class _MockHipBackend:
    def __init__(self, *, free: Any = None, residual_value: float = 0.0) -> None:
        self.prepare_calls = 0
        self.evaluate_calls = 0
        self.free = np.asarray(
            free if free is not None else np.asarray([], dtype=np.int64),
            dtype=np.int64,
        )
        self._residual_value = float(residual_value)

    def evaluate(self, states: Any, *args: Any, **kwargs: Any) -> tuple[np.ndarray, dict[str, Any]]:
        self.evaluate_calls += 1
        states_np = np.asarray(states, dtype=np.float64)
        batch_size = int(states_np.shape[0]) if states_np.ndim >= 2 else 1
        residual = np.full(
            (batch_size, int(self.free.size)),
            self._residual_value,
            dtype=np.float64,
        )
        return residual, {
            "batch_size": batch_size,
            "free_dof_count": int(self.free.size),
            "mock_hip_backend": True,
        }

    @classmethod
    def prepare(cls, **kwargs: Any) -> "_MockHipBackend":
        return cls(free=kwargs.get("free"))


class _MockHipBackendNonZero(_MockHipBackend):
    @classmethod
    def prepare(cls, **kwargs: Any) -> "_MockHipBackendNonZero":
        return cls(free=kwargs.get("free"), residual_value=1.0)


class _MockHipBackendPrepareFails:
    @classmethod
    def prepare(cls, **kwargs: Any) -> "_MockHipBackendPrepareFails":
        raise RuntimeError("hip_full_residual_binary_build_failed")


def test_frozen_shell_material_hip_replay_global_krylov_records_frozen_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert global_krylov["attempted"] is True
    assert global_krylov["frozen_shell_material_tangent_hip_replay"] is True
    assert global_krylov["shell_material_tangent_frozen_from_current_state"] is True
    assert (
        global_krylov.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )
    assert global_krylov.get("batch_replay_backend_disabled_reason") is None


def test_frozen_shell_material_hip_replay_without_frozen_flag_disables_global_krylov(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=False,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert (
        global_krylov["batch_replay_backend_disabled_reason"]
        == "state_dependent_shell_material_tangent_requires_cpu_batch"
    )
    assert global_krylov.get("frozen_shell_material_tangent_hip_replay") is None
    assert global_krylov.get("shell_material_tangent_frozen_from_current_state") is None


def test_frozen_shell_material_hip_replay_row_correction_records_frozen_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["attempted"] is True
    assert row_correction["frozen_shell_material_tangent_hip_replay"] is True
    assert row_correction["shell_material_tangent_frozen_from_current_state"] is True
    assert (
        row_correction.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )


def test_row_correction_per_state_hip_batch_replay_records_trial_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_per_state_batch_replay=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["per_state_batch_replay_enabled"] is True
    assert row_correction["per_state_batch_replay_state_count"] > 0
    assert row_correction.get("batch_replay_backend_disabled_reason") is None
    assert any(
        row.get("per_state_batch_replay") is True
        and row.get("hip_full_residual_batch_replay") is True
        for row in row_correction["trial_rows"]
    )
    gate = payload["gate_assessment"]
    assert gate["full_load_closure_passed"] is False
    assert gate["full_load_closure_gate"]["observed_load_scale"] == 0.656
    assert "full_load_gate_not_closed" in payload["blockers"]
    assert "does not close full G1" in payload["claim_boundary"]
    assert "sub-full-load diagnostic evidence" in payload["claim_boundary"]


def test_frozen_shell_material_hip_replay_without_frozen_flag_disables_row_correction(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=False,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["attempted"] is True
    assert (
        row_correction["batch_replay_backend_disabled_reason"]
        == "state_dependent_shell_material_tangent_requires_cpu_batch"
    )
    assert row_correction.get("frozen_shell_material_tangent_hip_replay") is None


def test_frozen_shell_material_hip_replay_blocks_on_backend_prepare_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendPrepareFails.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert global_krylov["frozen_shell_material_tangent_hip_replay"] is True
    assert global_krylov["hip_batch_replay_required_unavailable"] is True
    assert (
        global_krylov["hip_batch_replay_required_unavailable_reason"]
        == "hip_backend_prepare_failed_or_disabled"
    )
    assert global_krylov["cpu_batch_replay_fallback_suppressed"] is True
    assert global_krylov.get("batch_replay_backend_error") == "hip_full_residual_binary_build_failed"


def test_frozen_shell_material_hip_replay_row_correction_blocks_on_prepare_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendPrepareFails.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["attempted"] is True
    assert row_correction["frozen_shell_material_tangent_hip_replay"] is True
    assert row_correction["hip_batch_replay_required_unavailable"] is True
    assert (
        row_correction["hip_batch_replay_required_unavailable_reason"]
        == "hip_backend_prepare_failed_or_disabled"
    )
    assert row_correction["cpu_batch_replay_fallback_suppressed"] is True
    assert (
        row_correction.get("batch_replay_backend_error")
        == "hip_full_residual_binary_build_failed"
    )


def test_frozen_shell_material_hip_replay_does_not_claim_material_newton_closure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov.get("material_newton_closure") is None
    assert global_krylov.get("direct_residual_closure") is None
    assert "not state-dependent material Newton closure" in payload["claim_boundary"]
    assert (
        payload["residual_contract"][
            "frozen_shell_material_tangent_hip_replay_is_not_material_newton_closure"
        ]
        is True
    )
    assert payload["residual_contract"]["material_newton_gate_passed"] is False
    assert payload["gate_assessment"]["material_newton_breadth_passed"] is False
    assert (
        payload["residual_contract"]["consistent_residual_jacobian_newton_gate_passed"]
        is False
    )
    assert (
        payload["gate_assessment"]["consistent_residual_jacobian_newton_passed"]
        is False
    )
    assert (
        "material_newton_breadth_not_proven"
        in payload["gate_assessment"]["material_newton_breadth_blockers"]
    )
    material_meta = payload.get("shell_material")
    if isinstance(material_meta, dict):
        assert material_meta.get("material_newton_gate_passed") is None


def test_frozen_shell_material_hip_no_shell_material_tangent_default_behavior_unchanged(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=False,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert global_krylov.get("frozen_shell_material_tangent_hip_replay") is None
    assert (
        global_krylov.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )


def test_state_dependent_shell_material_hip_replay_global_krylov_records_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert global_krylov["attempted"] is True
    assert global_krylov.get("state_dependent_shell_material_tangent_hip_replay") is True
    assert (
        global_krylov.get("state_dependent_shell_material_tangent_operator_refresh_backend")
        == "host_shell_operator_refresh"
    )
    assert (
        global_krylov.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )


def test_state_dependent_flag_suppresses_frozen_disabled_reason(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        allow_frozen_shell_material_tangent_hip_replay=False,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov.get("state_dependent_shell_material_tangent_hip_replay") is True
    assert (
        global_krylov.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )
    assert global_krylov.get("batch_replay_backend_disabled_reason") is None


def test_state_dependent_path_suppresses_cpu_fallback_on_hip_prepare_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendPrepareFails.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["enabled"] is True
    assert global_krylov["hip_batch_replay_required_unavailable"] is True
    assert (
        global_krylov["hip_batch_replay_required_unavailable_reason"]
        == "hip_backend_prepare_or_evaluate_failed_state_dependent"
    )
    assert global_krylov["cpu_batch_replay_fallback_suppressed"] is True
    assert (
        global_krylov.get("batch_replay_backend_error")
        == "hip_full_residual_binary_build_failed"
    )


def test_state_dependent_row_correction_records_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["attempted"] is True
    assert row_correction.get("state_dependent_shell_material_tangent_hip_replay") is True
    assert (
        row_correction.get(
            "state_dependent_shell_material_tangent_operator_refresh_backend"
        )
        == "host_shell_operator_refresh"
    )
    assert (
        row_correction.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )


def test_state_dependent_row_correction_suppresses_cpu_fallback_on_prepare_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendPrepareFails.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["hip_batch_replay_required_unavailable"] is True
    assert (
        row_correction["hip_batch_replay_required_unavailable_reason"]
        == "hip_backend_prepare_or_evaluate_failed_state_dependent"
    )
    assert row_correction["cpu_batch_replay_fallback_suppressed"] is True
    assert (
        row_correction.get("batch_replay_backend_error")
        == "hip_full_residual_binary_build_failed"
    )


def test_state_dependent_claim_boundary_conservative_for_host_operator_refresh(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    assert (
        "Shell CSR/operator refresh happens on host" in payload["claim_boundary"]
    )
    assert (
        "not full production ROCm/HIP residency closure" in payload["claim_boundary"]
    )
    assert (
        payload["residual_contract"][
            "state_dependent_shell_material_tangent_hip_replay_is_not_production_residency"
        ]
        is True
    )
    assert payload["residual_contract"]["material_newton_gate_passed"] is False
    assert payload["residual_contract"]["state_dependent_material_newton_closure_passed"] is False
    assert payload["residual_contract"]["consistent_residual_jacobian_newton_gate_passed"] is False
    assert payload["gate_assessment"]["material_newton_breadth_passed"] is False
    assert payload["gate_assessment"]["consistent_residual_jacobian_newton_passed"] is False
    assert (
        "state_dependent_host_shell_operator_refresh_not_production_rocm_hip_residency"
        in payload["gate_assessment"]["material_newton_breadth_blockers"]
    )


def test_state_dependent_flag_wins_over_frozen_flag(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov.get("state_dependent_shell_material_tangent_hip_replay") is True
    assert (
        global_krylov.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )
    assert global_krylov.get("batch_replay_backend_disabled_reason") is None


class _ShellMaterialTangentSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *, node_xyz: Any, u: Any, elem_type_code: Any, elem_material_id: Any, conn_ptr: Any, conn_idx: Any, material_props: Any, controlled_probe: bool = False, **kwargs: Any) -> tuple[dict[int, float], dict[str, Any]]:
        self.calls.append({
            "u_copy": np.asarray(u, dtype=np.float64).copy(),
            "controlled_probe": bool(controlled_probe),
        })
        return {}, {"shell_material_tangent_surface_element_count": 0, "shell_material_tangent_state_bounded_element_count": 0}


class _ShellOperatorSpy:
    def __init__(self, wrapped: Any) -> None:
        self._wrapped = wrapped
        self.calls: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(
            {
                "u_copy": np.asarray(kwargs.get("u"), dtype=np.float64).copy(),
                "has_material_tangent": (
                    kwargs.get("material_tangent_by_surface_index_mpa") is not None
                ),
            }
        )
        return self._wrapped(*args, **kwargs)

    @property
    def material_tangent_states(self) -> list[np.ndarray]:
        return [
            call["u_copy"]
            for call in self.calls
            if bool(call.get("has_material_tangent"))
        ]


def _mock_torch_hip_gmres_once(
    matvec: Any,
    rhs: np.ndarray,
    *,
    restart: int,
) -> tuple[np.ndarray, int, dict[str, Any]]:
    rhs_np = np.asarray(rhs, dtype=np.float64)
    correction = np.full_like(rhs_np, 1.0e-6, dtype=np.float64)
    return correction, 0, {
        "linear_solver_backend": "torch_hip_gmres",
        "torch_hip_vector_algebra": True,
        "hip_krylov_solver_used": True,
        "mock_torch_hip_gmres": True,
        "krylov_restart": int(restart),
    }


def test_state_dependent_global_krylov_passes_candidate_states_to_shell_material_tangent(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """
    Prove that global state-dependent HIP replay passes the candidate state `u`
    into `shell_material_tangent_by_surface_index`, not only the current accepted/base state.
    """
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendNonZero.prepare,
    )
    monkeypatch.setattr(
        direct_probe,
        "_torch_hip_gmres_once",
        _mock_torch_hip_gmres_once,
    )
    spy = _ShellMaterialTangentSpy()
    monkeypatch.setattr(
        direct_probe, "shell_material_tangent_by_surface_index", spy
    )
    operator_spy = _ShellOperatorSpy(direct_probe._cached_shell_operator)
    monkeypatch.setattr(direct_probe, "_cached_shell_operator", operator_spy)

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["attempted"] is True
    assert global_krylov["base_residual_source"] == "hip_full_residual_batch_replay"
    assert global_krylov["base_residual_hip_full_residual_batch_replay"] is True
    assert global_krylov.get("hip_krylov_solver_used") is True
    assert any(
        row.get("hip_full_residual_batch_replay")
        for row in global_krylov.get("trial_rows", [])
    )
    assert len(spy.calls) >= 2, (
        "Expected at least 2 calls: base state + at least 1 candidate state probe"
    )
    replay_states = operator_spy.material_tangent_states
    assert len(replay_states) >= 2
    base_state = replay_states[0]
    assert any(not np.allclose(state, base_state) for state in replay_states[1:]), (
        "Expected at least one shell_material_tangent_by_surface_index call "
        "with a candidate state different from the base state in HIP replay"
    )


def test_global_krylov_hip_trial_alpha_candidates_use_batch_replay(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendNonZero.prepare,
    )
    monkeypatch.setattr(
        direct_probe,
        "_torch_hip_gmres_once",
        _mock_torch_hip_gmres_once,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
        matrix_free_global_krylov_alpha_values=(1.0, 0.5, 0.25),
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["attempted"] is True
    assert global_krylov["hip_batch_eval_count"] >= 2
    trial_rows = global_krylov.get("trial_rows", [])
    assert len(trial_rows) >= 3
    assert all(row.get("hip_full_residual_batch_replay") is True for row in trial_rows)
    assert any(
        row.get("hip_batch_group_size", 0) >= 3
        for row in trial_rows
    )


def test_global_krylov_central_jvp_probes_use_hip_batch_replay(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendNonZero.prepare,
    )
    def mock_torch_hip_gmres_with_matvec(
        matvec: Any,
        rhs: np.ndarray,
        *,
        restart: int,
    ) -> tuple[np.ndarray, int, dict[str, Any]]:
        rhs_np = np.asarray(rhs, dtype=np.float64)
        correction = np.full_like(rhs_np, 1.0e-6, dtype=np.float64)
        _ = matvec(correction)
        return correction, 0, {
            "linear_solver_backend": "torch_hip_gmres",
            "torch_hip_vector_algebra": True,
            "hip_krylov_solver_used": True,
            "mock_torch_hip_gmres": True,
            "krylov_restart": int(restart),
        }

    monkeypatch.setattr(
        direct_probe,
        "_torch_hip_gmres_once",
        mock_torch_hip_gmres_with_matvec,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_difference_scheme="central",
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
        matrix_free_global_krylov_alpha_values=(1.0,),
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov["attempted"] is True
    assert global_krylov["difference_scheme"] == "central"
    jvp_rows = global_krylov.get("jvp_rows", [])
    assert jvp_rows
    assert all(row["hip_full_residual_batch_replay"] is True for row in jvp_rows)
    assert all(row["minus_hip_full_residual_batch_replay"] is True for row in jvp_rows)
    assert all(row["hip_batch_group_size"] == 2 for row in jvp_rows)
    assert all(row["minus_hip_batch_group_size"] == 2 for row in jvp_rows)
    assert all(row["hip_batch_group_index"] == 0 for row in jvp_rows)
    assert all(row["minus_hip_batch_group_index"] == 1 for row in jvp_rows)


def test_state_dependent_row_correction_passes_each_candidate_state_to_shell_material_tangent(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """
    Prove that row state-dependent HIP replay passes EACH candidate state
    into `shell_material_tangent_by_surface_index` individually.
    """
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendNonZero.prepare,
    )
    spy = _ShellMaterialTangentSpy()
    monkeypatch.setattr(
        direct_probe, "shell_material_tangent_by_surface_index", spy
    )
    operator_spy = _ShellOperatorSpy(direct_probe._cached_shell_operator)
    monkeypatch.setattr(direct_probe, "_cached_shell_operator", operator_spy)

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
        current_tangent_residual_row_target_counts=(2,),
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["enabled"] is True
    assert row_correction["attempted"] is True
    assert row_correction.get("state_dependent_shell_material_tangent_hip_replay") is True
    assert len(spy.calls) >= 2, (
        "Expected at least 2 calls to shell_material_tangent_by_surface_index "
        "for row state-dependent replay"
    )
    all_recorded_us = operator_spy.material_tangent_states
    unique_hashes = {tuple(u.tobytes()) for u in all_recorded_us}
    assert len(unique_hashes) >= 2, (
        f"Expected at least 2 unique candidate states in calls, "
        f"got {len(unique_hashes)}"
    )


def test_row_correction_alpha_candidates_record_hip_batch_group_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendNonZero.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        max_current_tangent_residual_row_corrections=1,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
        current_tangent_residual_row_alpha_values=(0.125, 0.0625, 0.03125),
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    trial_rows = row_correction["trial_rows"]
    assert row_correction["batch_alpha_replay_batch_count"] >= 1
    assert trial_rows
    assert any(
        row["hip_full_residual_batch_replay"]
        and row["residual_batch_backend"] == "hip_full_residual"
        and row["hip_batch_group_size"] > 1
        and row["residual_row_batch_group_size"] == row["hip_batch_group_size"]
        and row["batch_alpha_replay_index"] == row["hip_batch_group_index"]
        for row in trial_rows
    )


def test_hip_residual_engine_contract_blocks_required_unattempted_component() -> None:
    contract = direct_probe._g1_hip_residual_engine_contract(
        {},
        {
            "enabled": True,
            "attempted": False,
            "promoted_to_final_state": False,
            "require_hip_batch_replay": True,
            "batch_replay_backend": "hip_full_residual",
        },
    )

    assert contract["hip_residual_engine_required"] is True
    assert contract["hip_residual_engine_contract_passed"] is False
    assert (
        "current_tangent_residual_row_correction::hip_required_component_not_attempted"
        in contract["hip_residual_engine_blockers"]
    )
    row = next(
        row
        for row in contract["hip_residual_engine_rows"]
        if row["component"] == "current_tangent_residual_row_correction"
    )
    assert row["active"] is True
    assert row["attempted"] is False
    assert row["promoted_to_final_state"] is False
    assert row["passed"] is False


def test_row_correction_fd_jacobian_records_hip_batch_group_metadata(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendNonZero.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        max_current_tangent_residual_row_corrections=1,
        current_tangent_residual_row_jacobian_mode="finite_difference",
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_fd_replay=True,
        current_tangent_residual_row_batch_alpha_replay=True,
        current_tangent_residual_row_support_column_counts=(4,),
        current_tangent_residual_row_fd_max_support_columns=4,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    candidate_rows = row_correction["passes"][0]["candidate_rows"]
    jacobian_rows = [row["jacobian"] for row in candidate_rows]
    assert row_correction["batch_fd_replay_batch_count"] >= 1
    assert any(
        jacobian["finite_difference_hip_batch_replay"]
        and "hip_full_residual" in jacobian["finite_difference_residual_batch_backends"]
        and jacobian["finite_difference_hip_batch_group_sizes"]
        for jacobian in jacobian_rows
    )


def test_row_correction_hip_required_multipass_stops_without_cpu_tangent_refresh(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        max_current_tangent_residual_row_corrections=2,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["promotion_count"] == 1
    assert (
        row_correction["stop_reason"]
        == "hip_required_row_tangent_refresh_unavailable_after_promotion"
    )
    assert row_correction["accepted_state_refresh_backend"] == "hip_full_residual"
    assert row_correction["accepted_state_refresh_hip_used"] is True
    assert row_correction["accepted_state_refresh_cpu_used"] is False
    assert (
        row_correction["accepted_state_tangent_refresh_backend"]
        == "not_refreshed_hip_required_row_correction"
    )
    assert row_correction["accepted_state_tangent_refresh_cpu_used"] is False
    assert row_correction["stop_after_hip_residual_promotion"] is True
    fallback_zero_audit = payload["gate_assessment"]["fallback_zero_audit"]
    boundaries = {
        boundary["boundary"]
        for boundary in fallback_zero_audit["fallback_zero_boundaries"]
    }
    assert "row_correction_cpu_residual_acceptance_refresh_used" not in boundaries
    assert "row_correction_cpu_tangent_refresh_used" not in boundaries
    assert "row_correction_hip_required_tangent_refresh_missing" in boundaries
    assert payload["gate_assessment"]["fallback_zero_passed"] is False


def test_row_correction_hip_required_fd_multipass_refreshes_tangent_with_hip_jvp(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        max_current_tangent_residual_row_corrections=2,
        current_tangent_residual_row_jacobian_mode="finite_difference",
        current_tangent_residual_row_support_selection="target_rows",
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_fd_replay=True,
        current_tangent_residual_row_batch_alpha_replay=True,
        current_tangent_residual_row_support_column_counts=(4,),
        current_tangent_residual_row_fd_max_support_columns=4,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["promotion_count"] == 1
    assert len(row_correction["passes"]) >= 2
    assert row_correction["accepted_state_refresh_backend"] == "hip_full_residual"
    assert row_correction["accepted_state_refresh_cpu_used"] is False
    assert (
        row_correction["accepted_state_tangent_refresh_backend"]
        == "hip_finite_difference_residual_jvp"
    )
    assert row_correction["accepted_state_tangent_refresh_hip_used"] is True
    assert row_correction["accepted_state_tangent_refresh_cpu_used"] is False
    assert row_correction["accepted_state_tangent_refresh_column_count"] > 0
    assert "frozen_support_graph_after_hip_residual_promotion" not in row_correction
    assert row_correction["support_selection"] == "target_rows"
    assert any(
        candidate["jacobian"]["stiffness_free_support_selection"]
        and not candidate["jacobian"]["support_selection_uses_tangent_stiffness"]
        and candidate["jacobian"]["finite_difference_hip_batch_replay"]
        for row_pass in row_correction["passes"]
        for candidate in row_pass.get("candidate_rows", [])
    )
    fallback_zero_audit = payload["gate_assessment"]["fallback_zero_audit"]
    boundaries = {
        boundary["boundary"]
        for boundary in fallback_zero_audit["fallback_zero_boundaries"]
    }
    assert "row_correction_cpu_residual_acceptance_refresh_used" not in boundaries
    assert "row_correction_cpu_tangent_refresh_used" not in boundaries
    assert "row_correction_hip_required_tangent_refresh_missing" not in boundaries
    assert payload["gate_assessment"]["fallback_zero_passed"] is True


def test_row_correction_terminal_hip_promotion_uses_hip_residual_refresh(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        enable_current_tangent_residual_row_correction=True,
        max_current_tangent_residual_row_corrections=1,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction["promotion_count"] == 1
    assert row_correction["accepted_state_refresh_backend"] == "hip_full_residual"
    assert row_correction["accepted_state_refresh_hip_used"] is True
    assert row_correction["accepted_state_refresh_cpu_used"] is False
    assert (
        row_correction["accepted_state_tangent_refresh_backend"]
        == "not_refreshed_terminal_row_correction"
    )
    assert row_correction["accepted_state_tangent_refresh_cpu_used"] is False
    fallback_zero_audit = payload["gate_assessment"]["fallback_zero_audit"]
    boundaries = {
        boundary["boundary"]
        for boundary in fallback_zero_audit["fallback_zero_boundaries"]
    }
    assert "row_correction_cpu_residual_acceptance_refresh_used" not in boundaries
    assert "row_correction_cpu_tangent_refresh_used" not in boundaries
    assert "row_correction_hip_required_tangent_refresh_missing" in boundaries


def test_state_dependent_spy_wins_behaviorally_over_frozen_when_both_flags_set(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """
    Behavioral proof: when both allow_state_dependent and allow_frozen flags
    are set, the state-dependent path passes candidate states into
    shell_material_tangent_by_surface_index (behavioral win over frozen mode).
    """
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackendNonZero.prepare,
    )
    monkeypatch.setattr(
        direct_probe,
        "_torch_hip_gmres_once",
        _mock_torch_hip_gmres_once,
    )
    spy = _ShellMaterialTangentSpy()
    monkeypatch.setattr(
        direct_probe, "shell_material_tangent_by_surface_index", spy
    )
    operator_spy = _ShellOperatorSpy(direct_probe._cached_shell_operator)
    monkeypatch.setattr(direct_probe, "_cached_shell_operator", operator_spy)

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_matrix_free_global_krylov=True,
        matrix_free_global_krylov_batch_replay_backend="hip_full_residual",
        matrix_free_global_krylov_require_hip_batch_replay=True,
    )

    global_krylov = payload["matrix_free_global_krylov"]
    assert global_krylov.get("state_dependent_shell_material_tangent_hip_replay") is True
    assert global_krylov.get("batch_replay_backend_disabled_reason") is None
    assert global_krylov.get("frozen_shell_material_tangent_hip_replay") is None
    replay_states = operator_spy.material_tangent_states
    assert len(replay_states) >= 2
    base_state = replay_states[0]
    state_dependent_calls_found = any(
        not np.allclose(state, base_state)
        for state in replay_states[1:]
    )
    assert state_dependent_calls_found, (
        "Expected state-dependent shell material tangent refresh with candidate states "
        "different from base, proving state-dependent wins over frozen when both flags set"
    )


def test_cached_shell_operator_bypasses_cache_when_material_tangent_override_nonempty(
    monkeypatch: Any,
) -> None:
    import implementation.phase1.mgt_shell_force_based_assembly as shell_mod

    assembly_call_count = 0

    def _fake_assemble(*, material_tangent_by_surface_index_mpa, **kwargs: Any) -> Any:
        nonlocal assembly_call_count
        assembly_call_count += 1
        n = int(np.asarray(kwargs["node_xyz"]).shape[0]) * 6
        from scipy.sparse import eye
        mat = eye(n, format="csr")
        return mat, np.zeros(n), {"fake": True, "overridden": bool(material_tangent_by_surface_index_mpa)}, []

    monkeypatch.setattr(
        shell_mod, "assemble_equilibrium_surface_shell_6dof", _fake_assemble
    )

    n_nodes = 4
    dofs = n_nodes * 6
    u = np.zeros(dofs, dtype=np.float64)
    node_xyz = np.zeros((n_nodes, 3), dtype=np.float64)
    elem_type_code = np.array([1], dtype=np.int32)
    elem_section_id = np.array([1], dtype=np.int32)
    elem_material_id = np.array([1], dtype=np.int32)
    conn_ptr = np.array([0, 3], dtype=np.int64)
    conn_idx = np.array([0, 1, 2], dtype=np.int64)
    material_props: dict[int, dict[str, Any]] = {1: {"E": 210e9}}
    plate_thickness_props: dict[int, dict[str, Any]] = {1: {"t": 0.01}}
    cache: dict[str, Any] = {}

    stiffness1, meta1, hit1 = shell_mod._cached_shell_operator(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
        shell_operator_cache=cache,
        material_tangent_by_surface_index_mpa=None,
    )
    assert hit1 is False, "First call should assemble (cold cache)"
    assert "shell_full_membrane_bending" in cache, "Should populate cache"
    cached_entry = cache["shell_full_membrane_bending"]
    assert cached_entry["stiffness"] is stiffness1

    prev_count = assembly_call_count
    stiffness2, meta2, hit2 = shell_mod._cached_shell_operator(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
        shell_operator_cache=cache,
        material_tangent_by_surface_index_mpa=None,
    )
    assert hit2 is True, "Second call without override should be cache hit"
    assert assembly_call_count == prev_count, "Assembly should NOT be called on cache hit"

    prev_count = assembly_call_count
    stiffness3, meta3, hit3 = shell_mod._cached_shell_operator(
        u=u,
        node_xyz=node_xyz,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        conn_ptr=conn_ptr,
        conn_idx=conn_idx,
        material_props=material_props,
        plate_thickness_props=plate_thickness_props,
        include_membrane=True,
        shell_operator_cache=cache,
        material_tangent_by_surface_index_mpa={0: 210e9},
    )
    assert hit3 is False, (
        "Third call WITH non-empty material_tangent_by_surface_index_mpa "
        "MUST bypass cache and re-assemble"
    )
    assert assembly_call_count == prev_count + 1, (
        "Assembly should be called when material tangent override is non-empty"
    )
    assert cached_entry["stiffness"] is stiffness1, (
        "Cache entry must NOT be overwritten when material tangent override is present"
    )
    assert stiffness3 is not stiffness1, (
        "Returned operator must be freshly assembled, not the cached one"
    )
    assert (
        meta3.get("shell_material_tangent_override_enabled") is True
    )
    assert (
        meta3.get("shell_material_tangent_operator_cache_disabled") is True
    )


def test_state_dependent_row_correction_state_dependent_flag_wins(
    tmp_path: Path, monkeypatch: Any
) -> None:
    mgt_path = tmp_path / "test.mgt"
    mgt_path.write_bytes(FIXTURE_MGT.read_bytes())
    checkpoint = tmp_path / "state.npz"
    _make_checkpoint_npz(checkpoint, dof_count=60)

    monkeypatch.setattr(
        direct_probe, "_rocm_hip_runtime_preflight", _mock_hip_preflight_available
    )
    monkeypatch.setattr(
        direct_probe.HipFullResidualBatchBackend,
        "prepare",
        _MockHipBackend.prepare,
    )

    payload = run_mgt_direct_residual_newton_probe(
        mgt_path=mgt_path,
        checkpoint_npz=checkpoint,
        apply_shell_material_tangent=True,
        allow_state_dependent_shell_material_tangent_hip_replay=True,
        allow_frozen_shell_material_tangent_hip_replay=True,
        enable_current_tangent_residual_row_correction=True,
        current_tangent_residual_row_batch_replay_backend="hip_full_residual",
        current_tangent_residual_row_require_hip_batch_replay=True,
        current_tangent_residual_row_use_residual_only_assembly=True,
        current_tangent_residual_row_batch_alpha_replay=True,
    )

    row_correction = payload["current_tangent_residual_row_correction"]
    assert row_correction.get("state_dependent_shell_material_tangent_hip_replay") is True
    assert (
        row_correction.get("batch_replay_backend_disabled_reason")
        != "state_dependent_shell_material_tangent_requires_cpu_batch"
    )
