from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_residual_jacobian_consistency_probe as probe_module  # noqa: E402
from run_mgt_residual_jacobian_consistency_probe import (  # noqa: E402
    _component_breakdown,
    _frame_hotspot_diagnostics,
    _hotspot_diagonal_newton_sweep,
    _hotspot_signed_displacement_sweep,
    _hotspot_tangent_fd_jvp_rows,
    _local_row_projection_diagnostics,
    _scalar_load_balance_diagnostics,
    _shell_internal_element_hotspot_diagnostics,
    _shell_membrane_hotspot_diagnostics,
    _shell_surface_load_hotspot_diagnostics,
    _state_scale_sweep,
    evaluate_residual_jacobian_direction,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import FrameElement  # noqa: E402


def test_evaluate_residual_jacobian_direction_matches_linear_residual() -> None:
    stiffness = coo_matrix(
        ([4.0, 2.0], ([0, 1], [0, 1])),
        shape=(2, 2),
    ).tocsc()
    f_ext = np.asarray([1.0, -3.0], dtype=np.float64)
    free = np.asarray([0, 1], dtype=np.int64)

    def assemble_residual(u: np.ndarray):
        residual = np.asarray(stiffness @ u - f_ext, dtype=np.float64)
        return stiffness, f_ext, free, residual, f_ext, {
            "physical_internal_force_model": "linear_fixture"
        }

    u0 = np.asarray([0.1, -0.2], dtype=np.float64)
    _k, _f, _free, residual, _rhs, _meta = assemble_residual(u0)
    row = evaluate_residual_jacobian_direction(
        u=u0,
        stiffness=stiffness,
        free=free,
        residual=residual,
        direction=np.asarray([1.0, -0.5], dtype=np.float64),
        assemble_residual=assemble_residual,
        fd_step=1.0e-7,
        direction_meta={"direction": "fixture"},
    )

    assert row["evaluated"] is True
    assert row["relative_l2_error"] <= 1.0e-8
    assert row["relative_inf_error"] <= 1.0e-8
    assert row["action_cosine"] > 0.999999


def test_evaluate_residual_jacobian_direction_reports_free_set_change() -> None:
    stiffness = coo_matrix(([1.0], ([0], [0])), shape=(1, 1)).tocsc()

    def assemble_residual(u: np.ndarray):
        free = np.asarray([], dtype=np.int64) if float(u[0]) > 0.0 else np.asarray([0], dtype=np.int64)
        residual = np.asarray([float(u[0])], dtype=np.float64)[: free.size]
        return stiffness, np.zeros(1), free, residual, np.zeros(free.size), {}

    row = evaluate_residual_jacobian_direction(
        u=np.asarray([0.0], dtype=np.float64),
        stiffness=stiffness,
        free=np.asarray([0], dtype=np.int64),
        residual=np.asarray([0.0], dtype=np.float64),
        direction=np.asarray([1.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        fd_step=1.0e-6,
        direction_meta={"direction": "fixture"},
    )

    assert row["evaluated"] is False
    assert row["reason"] == "free_dof_set_changed"


def test_component_breakdown_identifies_dominant_top_residual_component() -> None:
    free = np.asarray([0, 1, 2], dtype=np.int64)
    residual = np.asarray([5.0, -12.0, 2.0], dtype=np.float64)
    rhs = np.asarray([1.0, 2.0, 3.0], dtype=np.float64)
    row = _component_breakdown(
        component_forces={
            "frame": np.asarray([3.0, -1.0, 0.5], dtype=np.float64),
            "shell": np.asarray([2.0, -13.0, 1.5], dtype=np.float64),
            "spring": np.asarray([1.0, 2.0, 3.0], dtype=np.float64),
        },
        free=free,
        residual=residual,
        rhs=rhs,
        top_count=1,
    )

    assert row["top_rows"][0]["free_row"] == 1
    assert row["top_rows"][0]["dominant_component"] == "shell"
    assert row["top_row_dominant_component_counts"] == {"shell": 1}


def test_component_breakdown_marks_external_only_unassembled_top_row() -> None:
    row = _component_breakdown(
        component_forces={
            "frame": np.asarray([0.0], dtype=np.float64),
            "shell": np.asarray([0.0], dtype=np.float64),
        },
        free=np.asarray([0], dtype=np.int64),
        residual=np.asarray([-0.25], dtype=np.float64),
        rhs=np.asarray([0.25], dtype=np.float64),
        top_count=1,
    )

    assert row["top_rows"][0]["internal_sum_n"] == 0.0
    assert row["top_rows"][0]["dominant_component"] == "external_only_unassembled"
    assert row["top_row_dominant_component_counts"] == {
        "external_only_unassembled": 1
    }


def test_scalar_load_balance_diagnostics_fits_shell_top_row_external_scale() -> None:
    row = _scalar_load_balance_diagnostics(
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 0,
                "node_index": 0,
                "dof": "uz",
                "dominant_component": "shell_bending_drilling",
                "external_load_n": 4.0,
                "internal_sum_n": 1.0,
                "component_values_n": {"shell_bending_drilling": 1.0},
            },
            {
                "free_row": 1,
                "global_dof": 1,
                "node_index": 0,
                "dof": "uz",
                "dominant_component": "shell_membrane",
                "external_load_n": 2.0,
                "internal_sum_n": 0.5,
                "component_values_n": {"shell_membrane": 0.5},
            },
        ]
    )

    assert row["evaluated"] is True
    assert row["row_count"] == 2
    assert row["best_l2_external_scale"] == 0.25
    assert row["best_l2_scaled_residual_inf_n"] <= 1.0e-12
    assert row["required_external_scale_median"] == 0.25


def test_local_row_projection_diagnostics_reports_representable_rows() -> None:
    stiffness = coo_matrix(
        ([2.0, 3.0], ([0, 1], [0, 1])),
        shape=(2, 2),
    ).tocsc()
    free = np.asarray([0, 1], dtype=np.int64)
    residual = np.asarray([4.0, 9.0], dtype=np.float64)
    row = _local_row_projection_diagnostics(
        stiffness=stiffness,
        free=free,
        residual=residual,
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 0,
                "node_index": 0,
                "dof": "ux",
                "dominant_component": "shell_bending_drilling",
                "residual_n": 4.0,
            },
            {
                "free_row": 1,
                "global_dof": 1,
                "node_index": 0,
                "dof": "uy",
                "dominant_component": "shell_membrane",
                "residual_n": 9.0,
            },
        ],
    )

    assert row["evaluated"] is True
    assert row["selected_row_count"] == 2
    assert row["support_size"] == 2
    assert row["rank"] == 2
    assert row["projection_residual_inf_n"] <= 1.0e-12
    assert row["coefficient_linf"] == 3.0


def test_state_scale_sweep_reports_residual_growth() -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    f_ext = np.asarray([1.0], dtype=np.float64)

    def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
        residual = np.asarray(stiffness @ u - f_ext, dtype=np.float64)
        meta = {}
        if include_component_forces:
            meta["component_forces"] = {
                "frame": np.asarray(stiffness @ u, dtype=np.float64),
                "shell": np.zeros(1, dtype=np.float64),
            }
        return stiffness, f_ext, free, residual, f_ext, meta

    rows = _state_scale_sweep(
        u=np.asarray([1.0], dtype=np.float64),
        assemble_residual=assemble_residual,
        scale_values=(0.0, 0.1, 1.0),
    )

    assert rows[0]["residual_inf_n"] == 1.0
    assert rows[1]["residual_inf_n"] == 0.0
    assert rows[2]["residual_inf_n"] == 9.0


def test_hotspot_signed_displacement_sweep_tracks_gate_eligible_descent() -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)

    def assemble_residual(u: np.ndarray):
        residual = np.asarray([10.0 * float(u[0]) - 1.0], dtype=np.float64)
        return stiffness, np.asarray([1.0], dtype=np.float64), free, residual, np.asarray([1.0]), {}

    row = _hotspot_signed_displacement_sweep(
        u=np.asarray([0.2], dtype=np.float64),
        free=free,
        top_rows=[
            {
                "global_dof": 0,
                "dof": "ux",
                "dominant_component": "frame",
                "residual_n": 1.0,
            }
        ],
        assemble_residual=assemble_residual,
        step_values=(1.0e-6, 1.0e-5),
        relative_increment_tolerance=1.0e-4,
    )

    assert row["evaluated"] is True
    assert row["best_candidate"]["direct_residual_inf_n"] < row["base_direct_residual_inf_n"]
    assert row["best_gate_eligible_candidate"]["step_m"] == 1.0e-5
    assert row["best_gate_eligible_candidate"]["relative_increment_gate_passed"] is True


def test_hotspot_tangent_fd_jvp_rows_match_linear_fixture() -> None:
    stiffness = coo_matrix(
        ([4.0, 1.5, 1.5, 3.0], ([0, 0, 1, 1], [0, 1, 0, 1])),
        shape=(2, 2),
    ).tocsc()
    free = np.asarray([0, 1], dtype=np.int64)
    f_ext = np.asarray([1.0, -2.0], dtype=np.float64)

    def assemble_residual(u: np.ndarray):
        residual = np.asarray(stiffness @ u - f_ext, dtype=np.float64)
        return stiffness, f_ext, free, residual, f_ext, {
            "physical_internal_force_model": "linear_fixture"
        }

    u0 = np.asarray([0.2, -0.1], dtype=np.float64)
    _k, _f, _free, residual, _rhs, _meta = assemble_residual(u0)
    rows = _hotspot_tangent_fd_jvp_rows(
        u=u0,
        stiffness=stiffness,
        free=free,
        residual=residual,
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 0,
                "node_index": 0,
                "dof": "ux",
                "dominant_component": "frame",
                "residual_n": float(residual[0]),
                "component_values_n": {"frame": 1.0},
            }
        ],
        assemble_residual=assemble_residual,
        fd_step=1.0e-7,
    )

    assert rows[0]["evaluated"] is True
    assert rows[0]["selected_row_tangent_action_n_per_m"] == 4.0
    assert abs(rows[0]["selected_row_fd_action_n_per_m"] - 4.0) <= 1.0e-8
    assert rows[0]["selected_row_relative_error"] <= 1.0e-8
    assert rows[0]["relative_l2_error"] <= 1.0e-8


def test_hotspot_tangent_fd_jvp_rows_can_target_shell_bending_fast_path() -> None:
    stiffness = coo_matrix(
        ([4.0, 2.5], ([0, 1], [0, 1])),
        shape=(2, 2),
    ).tocsc()
    free = np.asarray([0, 1], dtype=np.int64)
    f_ext = np.asarray([0.5, -1.0], dtype=np.float64)
    calls = {"residual_only": 0, "full": 0}

    def assemble_residual(
        u: np.ndarray,
        *,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
    ):
        if residual_only:
            calls["residual_only"] += 1
        else:
            calls["full"] += 1
        trial_free = free if free_override is None else np.asarray(free_override, dtype=np.int64)
        residual = np.asarray(stiffness @ u - f_ext, dtype=np.float64)[trial_free]
        return stiffness, f_ext, trial_free, residual, f_ext[trial_free], {
            "physical_internal_force_model": "linear_fixture"
        }

    u0 = np.asarray([0.2, -0.4], dtype=np.float64)
    _k, _f, _free, residual, _rhs, _meta = assemble_residual(u0)
    rows = _hotspot_tangent_fd_jvp_rows(
        u=u0,
        stiffness=stiffness,
        free=free,
        residual=residual,
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 0,
                "node_index": 0,
                "dof": "ux",
                "dominant_component": "frame",
                "residual_n": float(residual[0]),
                "component_values_n": {"frame": float(residual[0])},
            },
            {
                "free_row": 1,
                "global_dof": 1,
                "node_index": 0,
                "dof": "uy",
                "dominant_component": "shell_bending_drilling",
                "residual_n": float(residual[1]),
                "component_values_n": {"shell_bending_drilling": 7.25},
            },
        ],
        assemble_residual=assemble_residual,
        fd_step=1.0e-7,
        max_rows=1,
        component_filter="shell_bending_drilling",
    )

    assert len(rows) == 1
    assert rows[0]["evaluated"] is True
    assert rows[0]["dominant_component"] == "shell_bending_drilling"
    assert rows[0]["global_dof"] == 1
    assert rows[0]["component_value_n"] == 7.25
    assert rows[0]["residual_only_assembly"] is True
    assert rows[0]["selected_row_tangent_action_n_per_m"] == 2.5
    assert abs(rows[0]["selected_row_fd_action_n_per_m"] - 2.5) <= 1.0e-8
    assert rows[0]["relative_inf_error"] <= 1.0e-8
    assert calls == {"residual_only": 1, "full": 1}


def test_hotspot_diagonal_newton_sweep_reduces_linear_hotspot_residual() -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)

    def assemble_residual(u: np.ndarray):
        residual = np.asarray([10.0 * float(u[0]) - 1.0], dtype=np.float64)
        return stiffness, np.asarray([1.0], dtype=np.float64), free, residual, np.asarray([1.0]), {}

    u0 = np.asarray([0.2], dtype=np.float64)
    row = _hotspot_diagonal_newton_sweep(
        u=u0,
        stiffness=stiffness,
        free=free,
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 0,
                "node_index": 0,
                "dof": "ux",
                "dominant_component": "frame",
                "residual_n": 1.0,
            }
        ],
        assemble_residual=assemble_residual,
        alpha_values=(1.0, 0.5),
    )

    assert row["evaluated"] is True
    assert row["selected_corrections"][0]["unit_alpha_correction_m"] == -0.1
    assert row["best_candidate"]["alpha"] == 1.0
    assert row["best_candidate"]["direct_residual_inf_n"] <= 1.0e-12
    assert abs(row["candidate_rows"][1]["direct_residual_inf_n"] - 0.5) <= 1.0e-12


def test_component_only_probe_skips_jvp_and_state_scale(monkeypatch) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    calls = {"assemble": 0}

    def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
        calls["assemble"] += 1
        residual = np.asarray([5.0], dtype=np.float64)
        meta = {"physical_internal_force_model": "fixture"}
        if include_component_forces:
            meta["component_forces"] = {
                "frame": np.asarray([4.0], dtype=np.float64),
                "shell_membrane": np.asarray([1.0], dtype=np.float64),
            }
        return stiffness, np.zeros(1), free, residual, np.ones(1), meta

    def build_direct_residual_assembler(**_kwargs):
        return assemble_residual, {
            "u0": np.asarray([0.0], dtype=np.float64),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_residual_jacobian_consistency_probe(
        output_json=None,
        component_only=True,
    )

    assert calls["assemble"] == 1
    assert payload["component_only"] is True
    assert payload["direction_rows"] == []
    assert payload["state_scale_sweep"] == []
    assert payload["residual_component_breakdown"]["component_inf_n"]["frame"] == 4.0
    assert payload["blockers"] == ["component_only_diagnostic_not_consistency_closure"]


def test_hip_required_probe_blocks_without_cpu_fallback(monkeypatch) -> None:
    def build_direct_residual_assembler(**_kwargs):
        raise AssertionError("HIP-required probe must not use the CPU diagnostic assembler")

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(
        probe_module,
        "_git_head",
        lambda: "fixture-commit",
    )
    monkeypatch.setattr(
        probe_module,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "fixture-time",
            "hip_available": False,
            "unavailable_reason": "fixture_no_hip",
            "runtime_blockers": ["dev_kfd_missing", "dev_dri_missing"],
        },
    )

    payload = probe_module.run_mgt_residual_jacobian_consistency_probe(
        output_json=None,
        component_only=True,
        require_hip_residual_engine=True,
    )

    assert payload["status"] == "partial"
    assert payload["source_commit_sha"] == "fixture-commit"
    assert payload["reused_evidence"] is False
    assert payload["rocm_hip_required"] is True
    assert payload["execution_mode"] == "hip_required_runtime_unavailable_no_cpu_fallback"
    assert payload["cpu_diagnostic_assembler_used"] is False
    assert payload["production_hip_residual_jacobian_path"] is False
    assert payload["residual_jacobian_consistency_ready"] is False
    assert payload["consistent_residual_jacobian_newton_passed"] is False
    assert payload["consistent_residual_jacobian_newton_gate_passed"] is False
    assert payload["blockers"] == [
        "rocm_hip_runtime_unavailable",
        "hip_runtime::dev_kfd_missing",
        "hip_runtime::dev_dri_missing",
        "hip_residual_jacobian_consistency_not_executed",
    ]


def test_hip_required_probe_without_runtime_blocker_list_keeps_generic_blockers(
    monkeypatch,
) -> None:
    def build_direct_residual_assembler(**_kwargs):
        raise AssertionError("HIP-required probe must not use the CPU diagnostic assembler")

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(probe_module, "_git_head", lambda: "fixture-commit")
    monkeypatch.setattr(
        probe_module,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "fixture-time",
            "hip_available": False,
            "unavailable_reason": "fixture_no_hip",
        },
    )

    payload = probe_module.run_mgt_residual_jacobian_consistency_probe(
        output_json=None,
        component_only=True,
        require_hip_residual_engine=True,
    )

    assert payload["blockers"] == [
        "rocm_hip_runtime_unavailable",
        "hip_residual_jacobian_consistency_not_executed",
    ]
    assert payload["cpu_diagnostic_assembler_used"] is False
    assert payload["production_hip_residual_jacobian_path"] is False


def test_hip_required_probe_with_runtime_still_does_not_use_cpu_assembler(
    monkeypatch,
) -> None:
    calls = {"child": 0}

    def build_direct_residual_assembler(**_kwargs):
        raise AssertionError(
            "HIP-required proof must not use the CPU diagnostic assembler"
        )

    def run_mgt_direct_residual_newton_probe(**kwargs):
        calls["child"] += 1
        assert kwargs["enable_matrix_free_global_krylov"] is True
        assert kwargs["matrix_free_global_krylov_require_hip_batch_replay"] is True
        assert (
            kwargs["matrix_free_global_krylov_batch_replay_backend"]
            == "hip_full_residual_resident"
        )
        assert kwargs["matrix_free_global_krylov_linear_solver_backend"] == "torch_hip_gmres"
        assert kwargs["enable_current_tangent_residual_row_correction"] is True
        assert kwargs["current_tangent_residual_row_require_hip_batch_replay"] is True
        assert (
            kwargs["current_tangent_residual_row_batch_replay_backend"]
            == "hip_full_residual"
        )
        return {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "source_commit_sha": "fixture-commit",
            "reused_evidence": False,
            "status": "partial",
            "direct_residual_newton_ready": False,
            "checkpoint": {"load_scale": 0.656},
            "residual_contract": {
                "hip_residual_engine_required": True,
                "hip_residual_engine_contract_passed": False,
                "hip_residual_engine_blockers": [
                    "matrix_free_global_krylov::accepted_state_refresh_cpu_used"
                ],
                "consistent_residual_jacobian_newton_blockers": [
                    "consistent_residual_jacobian_newton_not_proven"
                ],
            },
            "gate_assessment": {
                "consistent_residual_jacobian_newton_passed": False,
                "consistent_residual_jacobian_newton_blockers": [
                    "consistent_residual_jacobian_newton_not_proven"
                ],
                "fallback_zero_passed": False,
            },
            "matrix_free_global_krylov": {
                "enabled": True,
                "attempted": True,
                "batch_replay_backend": "hip_full_residual_resident",
                "require_hip_batch_replay": True,
                "require_hip_krylov_solver": True,
                "hip_krylov_solver_used": True,
                "accepted_state_refresh_cpu_used": True,
            },
            "current_tangent_residual_row_correction": {
                "enabled": True,
                "attempted": True,
                "batch_replay_backend": "hip_full_residual",
                "require_hip_batch_replay": True,
                "accepted_state_refresh_cpu_used": False,
                "accepted_state_tangent_refresh_cpu_used": False,
            },
            "blockers": ["consistent_jacobian_or_globalization_required"],
        }

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(
        probe_module,
        "run_mgt_direct_residual_newton_probe",
        run_mgt_direct_residual_newton_probe,
    )
    monkeypatch.setattr(probe_module, "_git_head", lambda: "fixture-commit")
    monkeypatch.setattr(
        probe_module,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "fixture-time",
            "hip_available": True,
            "torch_importable": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
            "runtime_blockers": [],
        },
    )

    payload = probe_module.run_mgt_residual_jacobian_consistency_probe(
        output_json=None,
        component_only=False,
        require_hip_residual_engine=True,
    )

    assert payload["status"] == "partial"
    assert payload["source_commit_sha"] == "fixture-commit"
    assert payload["reused_evidence"] is False
    assert payload["rocm_hip_required"] is True
    assert payload["execution_mode"] == "hip_required_direct_probe_no_cpu_fallback"
    assert payload["cpu_diagnostic_assembler_used"] is False
    assert payload["production_hip_residual_jacobian_path"] is True
    assert payload["rocm_hip_runtime_preflight"]["hip_available"] is True
    assert payload["residual_jacobian_consistency_ready"] is False
    assert payload["consistent_residual_jacobian_newton_gate_passed"] is False
    assert payload["direction_rows"] == []
    assert payload["state_scale_sweep"] == []
    assert payload["runtime_metrics"]["base_assembly_seconds"] == 0.0
    assert "does not use this module's CPU diagnostic assembler" in payload["claim_boundary"]
    assert calls["child"] == 1
    assert payload["load_scale"] == 0.656
    assert payload["hip_direct_probe"]["executed"] is True
    assert payload["hip_direct_probe"]["production_hip_residual_jacobian_path"] is True
    assert (
        payload["hip_direct_probe"]["matrix_free_global_krylov"][
            "batch_replay_backend"
        ]
        == "hip_full_residual_resident"
    )
    assert (
        payload["hip_direct_probe"]["matrix_free_global_krylov"]["jvp_row_count"]
        == 0
    )
    assert (
        "hip_direct_probe_global_krylov_jvp_rows_missing"
        in payload["blockers"]
    )
    assert (
        "hip_direct_probe_hip_residual_engine_contract_not_closed"
        in payload["blockers"]
    )
    assert (
        "hip_direct_probe_consistent_residual_jacobian_not_closed"
        in payload["blockers"]
    )
    assert "hip_direct_probe_fallback_zero_not_closed" in payload["blockers"]


def test_hip_required_probe_can_pass_only_with_strict_child_hip_contract(
    monkeypatch,
) -> None:
    def build_direct_residual_assembler(**_kwargs):
        raise AssertionError(
            "HIP-required proof must not use the CPU diagnostic assembler"
        )

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(probe_module, "_git_head", lambda: "fixture-commit")
    monkeypatch.setattr(
        probe_module,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "fixture-time",
            "hip_available": True,
            "torch_importable": True,
            "torch_rocm_build": True,
            "torch_hip_device_available": True,
            "runtime_blockers": [],
        },
    )
    monkeypatch.setattr(
        probe_module,
        "run_mgt_direct_residual_newton_probe",
        lambda **_kwargs: {
            "schema_version": "mgt-direct-residual-newton-probe.v1",
            "source_commit_sha": "fixture-commit",
            "reused_evidence": False,
            "status": "partial",
            "direct_residual_newton_ready": False,
            "checkpoint": {"load_scale": 1.0},
            "residual_contract": {
                "hip_residual_engine_required": True,
                "hip_residual_engine_contract_passed": True,
                "hip_residual_engine_blockers": [],
                "consistent_residual_jacobian_newton_blockers": [],
            },
            "gate_assessment": {
                "consistent_residual_jacobian_newton_passed": True,
                "consistent_residual_jacobian_newton_blockers": [],
                "fallback_zero_passed": True,
            },
            "matrix_free_global_krylov": {
                "enabled": True,
                "attempted": True,
                "batch_replay_backend": "hip_full_residual_resident",
                "require_hip_batch_replay": True,
                "require_hip_krylov_solver": True,
                "hip_krylov_solver_used": True,
                "accepted_state_refresh_cpu_used": False,
                "jvp_rows": [
                    {
                        "direction": "fixture_global_jvp",
                        "hip_full_residual_batch_replay": True,
                        "jacobian_action_inf_n": 1.0,
                    }
                ],
            },
            "current_tangent_residual_row_correction": {
                "enabled": True,
                "attempted": True,
                "batch_replay_backend": "hip_full_residual",
                "require_hip_batch_replay": True,
                "accepted_state_refresh_cpu_used": False,
                "accepted_state_tangent_refresh_cpu_used": False,
            },
            "blockers": [],
        },
    )

    payload = probe_module.run_mgt_residual_jacobian_consistency_probe(
        output_json=None,
        require_hip_residual_engine=True,
    )

    assert payload["status"] == "ready"
    assert payload["residual_jacobian_consistency_ready"] is True
    assert payload["consistent_residual_jacobian_newton_gate_passed"] is True
    assert payload["production_hip_residual_jacobian_path"] is True
    assert payload["cpu_diagnostic_assembler_used"] is False
    assert payload["blockers"] == []
    assert payload["hip_direct_probe"]["direct_residual_newton_ready"] is False
    assert (
        payload["hip_direct_probe"]["matrix_free_global_krylov"]["jvp_row_count"]
        == 1
    )
    assert (
        payload["hip_direct_probe"]["matrix_free_global_krylov"][
            "jvp_rows_retained"
        ]
        is True
    )


def test_hip_required_cli_does_not_pass_component_only_without_hip(
    monkeypatch,
    tmp_path,
) -> None:
    def build_direct_residual_assembler(**_kwargs):
        raise AssertionError("HIP-required CLI must not use the CPU diagnostic assembler")

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(probe_module, "_git_head", lambda: "fixture-commit")
    monkeypatch.setattr(
        probe_module,
        "_rocm_hip_runtime_preflight",
        lambda: {
            "checked_at": "fixture-time",
            "hip_available": False,
            "unavailable_reason": "fixture_no_hip",
            "runtime_blockers": ["dev_kfd_missing"],
        },
    )

    receipt = tmp_path / "receipt.json"
    exit_code = probe_module.main(
        [
            "--component-only",
            "--require-hip-residual-engine",
            "--output-json",
            str(receipt),
        ]
    )

    assert exit_code == 2
    assert '"hip_runtime::dev_kfd_missing"' in receipt.read_text(encoding="utf-8")


def test_component_breakdown_probe_honors_top_residual_count(monkeypatch) -> None:
    stiffness = coo_matrix(([1.0, 1.0, 1.0], ([0, 1, 2], [0, 1, 2])), shape=(3, 3)).tocsc()
    free = np.asarray([0, 1, 2], dtype=np.int64)

    def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
        residual = np.asarray([5.0, -4.0, 3.0], dtype=np.float64)
        meta = {"physical_internal_force_model": "fixture"}
        if include_component_forces:
            meta["component_forces"] = {
                "frame": np.asarray([5.0, -4.0, 3.0], dtype=np.float64)
            }
        return stiffness, np.zeros(3), free, residual, np.ones(3), meta

    def build_direct_residual_assembler(**_kwargs):
        return assemble_residual, {
            "u0": np.zeros(3, dtype=np.float64),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_residual_jacobian_consistency_probe(
        output_json=None,
        component_only=True,
        top_residual_count=2,
    )

    rows = payload["residual_component_breakdown"]["top_rows"]
    assert payload["top_residual_count"] == 2
    assert [row["free_row"] for row in rows] == [0, 1]


def test_shell_membrane_hotspot_diagnostics_reports_global_dof_participation() -> None:
    setup_meta = {
        "_node_xyz": np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 0.0, 3.0],
            ],
            dtype=np.float64,
        ),
        "_elem_id": np.asarray([101], dtype=np.int64),
        "_elem_type_code": np.asarray([2], dtype=np.int32),
        "_conn_ptr": np.asarray([0, 3], dtype=np.int64),
        "_conn_idx": np.asarray([0, 1, 2], dtype=np.int64),
    }
    u = np.zeros(18, dtype=np.float64)
    u[2] = -0.2
    u[14] = 0.1
    rows = _shell_membrane_hotspot_diagnostics(
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 2,
                "node_index": 0,
                "dof": "uz",
                "dominant_component": "shell_membrane",
                "residual_n": 10.0,
            }
        ],
        u=u,
        setup_meta=setup_meta,
    )

    assert rows[0]["incident_surface_element_count"] == 1
    assert rows[0]["max_global_dof_membrane_participation"] > 0.99
    assert rows[0]["max_global_dof_normal_participation"] < 1.0e-12
    assert rows[0]["max_relative_membrane_displacement_m"] > 0.0
    assert rows[0]["sample_incident_elements"][0]["elem_id"] == 101


def test_shell_surface_load_hotspot_diagnostics_reconstructs_reference_load() -> None:
    setup_meta = {
        "_node_xyz": np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float64,
        ),
        "_node_id": np.asarray([10, 11, 12], dtype=np.int64),
        "_elem_id": np.asarray([101], dtype=np.int64),
        "_elem_type_code": np.asarray([2], dtype=np.int32),
        "_conn_ptr": np.asarray([0, 3], dtype=np.int64),
        "_conn_idx": np.asarray([0, 1, 2], dtype=np.int64),
        "load_scale": 2.0,
    }
    row = _shell_surface_load_hotspot_diagnostics(
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 2,
                "node_index": 0,
                "dof": "uz",
                "dominant_component": "shell_bending_drilling",
                "residual_n": -0.25,
                "external_load_n": 1.0 / 3.0,
                "component_values_n": {"shell_bending_drilling": 1.0 / 12.0},
            }
        ],
        setup_meta=setup_meta,
    )

    assert row["evaluated"] is True
    assert row["row_count"] == 1
    assert abs(row["external_minus_reference_shell_load_inf_n"]) <= 1.0e-12
    assert row["rows"][0]["raw_node_id"] == 10
    assert row["rows"][0]["reference_shell_load_reconstructed_n"] == 1.0 / 3.0
    assert row["rows"][0]["required_reference_shell_load_scale_for_zero_row_residual"] == 0.25
    assert row["rows"][0]["sample_incident_surface_elements"][0]["elem_id"] == 101


def test_shell_internal_element_hotspot_diagnostics_reconstructs_component_force() -> None:
    setup_meta = {
        "_node_xyz": np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float64,
        ),
        "_node_id": np.asarray([10, 11, 12], dtype=np.int64),
        "_elem_id": np.asarray([101], dtype=np.int64),
        "_elem_type_code": np.asarray([2], dtype=np.int32),
        "_elem_section_id": np.asarray([7], dtype=np.int32),
        "_elem_material_id": np.asarray([3], dtype=np.int32),
        "_conn_ptr": np.asarray([0, 3], dtype=np.int64),
        "_conn_idx": np.asarray([0, 1, 2], dtype=np.int64),
        "_material_props": {3: {"E_kN_per_m2": 210000.0, "poisson": 0.2}},
        "_plate_thickness_props": {7: {"effective_thickness_m": 0.2}},
        "load_scale": 2.0,
    }
    u = np.zeros(18, dtype=np.float64)
    u[2] = 0.001
    u[8] = -0.00025

    reconstructed = _shell_internal_element_hotspot_diagnostics(
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 2,
                "node_index": 0,
                "dof": "uz",
                "dominant_component": "shell_bending_drilling",
                "residual_n": 0.0,
                "external_load_n": 1.0 / 3.0,
                "component_values_n": {"shell_bending_drilling": 0.0, "shell_membrane": 0.0},
            }
        ],
        u=u,
        setup_meta=setup_meta,
    )
    shell_force = reconstructed["rows"][0]["reconstructed_shell_internal_force_n"]

    row = _shell_internal_element_hotspot_diagnostics(
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 2,
                "node_index": 0,
                "dof": "uz",
                "dominant_component": "shell_bending_drilling",
                "residual_n": 0.0,
                "external_load_n": 1.0 / 3.0,
                "component_values_n": {
                    "shell_bending_drilling": shell_force,
                    "shell_membrane": 0.0,
                },
            }
        ],
        u=u,
        setup_meta=setup_meta,
    )

    assert row["evaluated"] is True
    assert row["row_count"] == 1
    assert abs(row["component_minus_reconstructed_shell_inf_n"]) <= 1.0e-12
    hotspot = row["rows"][0]
    assert hotspot["raw_node_id"] == 10
    assert hotspot["sample_incident_surface_elements"][0]["elem_id"] == 101
    assert hotspot["sample_incident_surface_elements"][0]["source_thickness"] is True
    assert hotspot["reference_shell_load_reconstructed_n"] == 1.0 / 3.0
    assert hotspot["surface_component_element_count"] == 1
    assert hotspot["surface_component_frame_connected_node_count"] == 0
    assert hotspot["surface_component_restrained_translation_dof_count"] == 0
    assert hotspot["surface_component_free_pressure_resultant"] is True


def test_frame_hotspot_diagnostics_reconstructs_incident_frame_contribution() -> None:
    setup_meta = {
        "_node_xyz": np.asarray(
            [
                [0.0, 0.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        ),
        "_node_id": np.asarray([1001, 1002], dtype=np.int64),
        "_frame_elements": [
            FrameElement(
                elem_id=501,
                node_i=0,
                node_j=1,
                section_id=1,
                material_id=1,
                length_m=1.0,
            )
        ],
        "_section_props": {1: {"A_m2": 0.01, "Iy_m4": 1.0e-6, "Iz_m4": 1.0e-6}},
        "_material_props": {1: {"E_kN_per_m2": 1000.0, "poisson": 0.25}},
        "_base_axial_forces": {},
        "load_scale": 1.0,
        "frame_gravity_load_scale": 0.01,
    }
    u = np.zeros(12, dtype=np.float64)
    u[8] = 0.001

    rows = _frame_hotspot_diagnostics(
        top_rows=[
            {
                "free_row": 0,
                "global_dof": 8,
                "node_index": 1,
                "dof": "uz",
                "dominant_component": "frame",
                "residual_n": 12.0,
                "external_load_n": 2.0,
                "component_values_n": {"frame": 10.0},
            }
        ],
        u=u,
        setup_meta=setup_meta,
    )

    assert rows[0]["raw_node_id"] == 1002
    assert rows[0]["incident_frame_element_count"] == 1
    assert rows[0]["incident_frame_target_dof_contribution_sum_n"] == 10.0
    assert abs(rows[0]["component_reconstruction_error_n"]) <= 1.0e-12
    assert rows[0]["sample_incident_frame_elements"][0]["elem_id"] == 501
    assert (
        rows[0]["sample_incident_frame_elements"][0][
            "verticality_abs_dz_over_length"
        ]
        == 1.0
    )
