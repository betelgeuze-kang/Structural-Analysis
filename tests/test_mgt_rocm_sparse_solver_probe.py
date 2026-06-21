#!/usr/bin/env python3
"""Tests for the MGT ROCm sparse solver probe."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZATION_ROCM_RECEIPT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_rocm_sparse_solver_probe.json"
)
PRODUCTIZATION_ROCM_RUN_HISTORY = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_rocm_probe_run_history.json"
)
PRODUCTIZATION_ROCALUTION_SHELL_SWEEP = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_rocalution_shell_preconditioner_sweep.json"
)
PRODUCTIZATION_ROCALUTION_SAAMG_DEBUG_SWEEP = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_rocalution_shell_saamg_debug_sweep.json"
)
PRODUCTIZATION_STREAMED_LARGE_RAS_SHELL_PROBE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_streamed_large_ras_shell_probe.json"
)
PRODUCTIZATION_MULTIPLICATIVE_RAS_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_multiplicative_ras_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_COARSE_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_coarse_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_COARSE_SHELL_PROBE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_coarse_shell_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_SMOOTHED_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_smoothed_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_SMOOTHED_SHELL_PROBE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_smoothed_shell_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_REPEATED_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_repeated_coarse_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_REPEATED_SHELL_PROBE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_repeated_coarse_shell_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_WEIGHTED_SHELL_WEIGHT_SWEEP = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_weighted_shell_weight_sweep_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_SIGNED_SHELL_WEIGHT_SWEEP = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_signed_shell_weight_sweep_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_SHELL_WEIGHT_SWEEP = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_enriched_shell_weight_sweep_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_WEIGHT_SWEEP = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_shell_weight_sweep_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_FINE_WEIGHT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_shell_fine_weight_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_CURRENT_SINGLE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_enriched_restricted_coupled_current_single_probe.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_ORTHOGONALIZED_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_enriched_orthogonalized_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_ORTHOGONALIZED_COUPLED_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_rhs_enriched_orthogonalized_coupled_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_ENERGY_RESTRICTED_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_energy_restricted_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_RESTRICTED_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_restricted_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_MODE_COUNT_SWEEP_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_mode_count_sweep_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_SELECTION_SWEEP_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_selection_sweep_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_WEIGHT_PASS_SWEEP_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_weight_pass_sweep_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_SCHUR_CYCLE_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_schur_cycle_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_harmonic_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DEPTH_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_harmonic_depth_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_harmonic_qr_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_RESIDUAL_RESTRICTION_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_harmonic_residual_restriction_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DOF_FILTER_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_harmonic_dof_filter_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_ENERGY_ORTHOGONALIZATION_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_edge_geneo_harmonic_energy_orthogonalization_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_PAIR_DD_SMOOTHER_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_pair_dd_smoother_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_PAIR_DD_SWEPT_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_pair_dd_swept_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_PAIR_DD_COARSE_REBALANCE_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_pair_dd_coarse_rebalance_shell_smoke.json"
)
PRODUCTIZATION_INTERFACE_PAIR_DD_COARSE_REBALANCE_WEIGHT_SWEEP_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_interface_pair_dd_coarse_rebalance_weight_sweep_shell_smoke.json"
)
PRODUCTIZATION_COUPLING_HOTSPOT_CURRENT_COUPLED = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_coupling_hotspot_current_coupled_probe.json"
)
PRODUCTIZATION_RIGID_BODY_CURRENT_COUPLED_SMOKE_BASELINE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_rigid_body_current_coupled_smoke_baseline.json"
)
PRODUCTIZATION_RIGID_BODY_RESTRICTED_INTERFACE_HYBRID_COUPLED_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_smoke.json"
)
PRODUCTIZATION_RIGID_BODY_RESTRICTED_INTERFACE_HYBRID_COUPLED_TINY_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_rigid_body_restricted_interface_hybrid_coupled_tiny_smoke.json"
)
PRODUCTIZATION_RESIDUAL_REGION_DIAGNOSTIC_SHELL_SMOKE = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_dof_block_schur_residual_region_diagnostic_shell_smoke.json"
)
RUN_HEAVY_ROCM_TEST_ENV = "RUN_MGT_ROCM_HEAVY_GPU_TEST"
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_rocm_sparse_solver_probe as rocm_probe  # noqa: E402
from run_mgt_rocm_sparse_solver_probe import (  # noqa: E402
    _rocalution_preconditioned_krylov_candidates,
    _run_external_solver_bridge,
)


def test_rocalution_sweep_keeps_saamg_preconditioners_opt_in() -> None:
    candidates = _rocalution_preconditioned_krylov_candidates()
    opt_in_candidates = _rocalution_preconditioned_krylov_candidates(include_saamg=True)

    candidate_keys = {
        (
            row["solver"],
            row["preconditioner"],
            row["ilu_p"],
            row["ilu_q"],
            row["basis_size"],
        )
        for row in candidates
    }
    opt_in_keys = {
        (
            row["solver"],
            row["preconditioner"],
            row["ilu_p"],
            row["ilu_q"],
            row["basis_size"],
            row.get("amg_coarse_size"),
            row.get("amg_manual_smoothers"),
        )
        for row in opt_in_candidates
    }

    assert ("gmres", "multi_colored_ilu", 0, 1, 64) in candidate_keys
    assert ("gmres", "multi_colored_ilu", 1, 1, 64) in candidate_keys
    assert ("gmres", "ilut", 0, 15, 64) in candidate_keys
    assert ("gmres", "ic", 0, 1, 64) in candidate_keys
    assert not any(row["preconditioner"] == "saamg" for row in candidates)
    assert ("gmres", "saamg", 0, 1, 64, 256, False) in opt_in_keys
    assert ("saamg", "none", 0, 1, 64, 30000, False) in opt_in_keys


def test_torch_sparse_solver_attempts_hip_only_skips_host_fallback(monkeypatch) -> None:
    class FakeMatrix:
        shape = (2, 2)
        nnz = 2

    def not_converged(name: str) -> dict[str, object]:
        return {"backend": name, "converged": False}

    monkeypatch.setattr(
        rocm_probe,
        "_torch_sparse_cg",
        lambda **_kwargs: not_converged("rocm_torch_sparse_cg"),
    )
    monkeypatch.setattr(
        rocm_probe,
        "_torch_sparse_bicgstab",
        lambda **_kwargs: not_converged("rocm_torch_sparse_bicgstab"),
    )
    monkeypatch.setattr(
        rocm_probe,
        "_torch_sparse_symmetric_scaled_bicgstab",
        lambda **_kwargs: not_converged("rocm_torch_sparse_symmetric_scaled_bicgstab"),
    )
    monkeypatch.setattr(
        rocm_probe,
        "_rocalution_sparse_preconditioned_krylov_sweep",
        lambda **_kwargs: not_converged("rocalution_sparse_preconditioned_krylov"),
    )
    monkeypatch.setattr(rocm_probe, "_matrix_diagnostics", lambda _k_ff: {})

    def fail_host_fallback(**_kwargs):
        raise AssertionError("HIP-only solve must not call host ILU/CPU GMRES fallback")

    monkeypatch.setattr(
        rocm_probe,
        "_torch_sparse_host_ilu_device_gmres_sweep",
        fail_host_fallback,
    )

    result = rocm_probe._torch_sparse_solver_attempts(
        label="hip_only_unit",
        k_ff=FakeMatrix(),
        rhs=np.asarray([1.0, 0.0], dtype=np.float64),
        max_iterations=1,
        tolerance_abs=1.0e-6,
        tolerance_rel=1.0e-9,
        allow_host_fallback=False,
    )

    assert result["ready"] is False
    assert result["hip_only"] is True
    assert result["host_solver_fallback_allowed"] is False
    assert result["host_solver_fallback_skipped"] is True
    assert result["rocm_sparse_host_ilu_device_gmres"]["skipped"] is True
    assert result["rocm_sparse_block_bicgstab_ready"] is False
    assert result["rocm_sparse_post_schur_residual_row_block_lstsq_refinement_ready"] is False
    assert result["rocm_sparse_spsolve_supported"] is False
    assert result["blockers"] == ["hip_only_unit_hip_only_rocm_sparse_solver_not_converged"]


def test_hip_only_crash_wrapper_writes_blocked_receipt(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "hip_only_crash.json"
    captured: dict[str, object] = {}

    class FakeCompletedProcess:
        returncode = -6
        stdout = ""
        stderr = "Memory access fault by GPU node-1"

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeCompletedProcess()

    monkeypatch.setattr(rocm_probe.subprocess, "run", fake_run)

    rc = rocm_probe._run_hip_only_probe_with_crash_receipt(
        ["--hip-only", "--output-json", str(out)],
        output_json=out,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert rc == 3
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_ROCM_HIP_WORKER_ABORTED"
    assert payload["hip_only"] is True
    assert payload["host_solver_fallback_allowed"] is False
    assert payload["host_solver_fallback_skipped"] is True
    assert payload["worker_returncode"] == -6
    assert payload["worker_signal"] == "SIGABRT"
    assert "Memory access fault" in payload["worker_stderr_tail"]
    assert "rocm_hip_worker_aborted_before_receipt" in payload["blockers"]
    assert "--internal-no-crash-wrapper" in captured["command"]


def test_external_solver_bridge_timeout_kills_process_group() -> None:
    result = _run_external_solver_bridge(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ],
        env=dict(os.environ),
        timeout_seconds=1,
    )

    assert result["timed_out"] is True
    assert result["killed_process_group"] is True
    assert result["returncode"] is not None


def test_rocm_probe_run_history_is_separate_from_solver_receipt() -> None:
    assert PRODUCTIZATION_ROCM_RECEIPT.exists()
    assert PRODUCTIZATION_ROCM_RUN_HISTORY.exists()

    receipt = json.loads(PRODUCTIZATION_ROCM_RECEIPT.read_text(encoding="utf-8"))
    run_history = json.loads(PRODUCTIZATION_ROCM_RUN_HISTORY.read_text(encoding="utf-8"))

    assert "latest_official_probe_rerun" not in receipt
    assert run_history["schema_version"] == "mgt-rocm-probe-run-history.v1"
    assert isinstance(run_history["runs"], list)


def test_rocalution_focused_sweeps_record_unused_preconditioner_counterevidence() -> None:
    assert PRODUCTIZATION_ROCALUTION_SHELL_SWEEP.exists()
    assert PRODUCTIZATION_ROCALUTION_SAAMG_DEBUG_SWEEP.exists()

    sweep = json.loads(PRODUCTIZATION_ROCALUTION_SHELL_SWEEP.read_text(encoding="utf-8"))
    rows = sweep["rocalution_preconditioned_krylov"]["candidate_rows"]
    row_keys = {
        (row["solver"], row["preconditioner"], row["ilu_p"], row["ilu_q"])
        for row in rows
    }

    assert sweep["status"] == "partial"
    assert ("gmres", "multi_colored_ilu", 1, 1) in row_keys
    assert ("gmres", "ilut", 0, 15) in row_keys
    assert ("gmres", "ic", 0, 1) in row_keys
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in rows)

    saamg = json.loads(PRODUCTIZATION_ROCALUTION_SAAMG_DEBUG_SWEEP.read_text(encoding="utf-8"))
    saamg_rows = saamg["rocalution_preconditioned_krylov"]["candidate_rows"]
    default_saamg_rows = [
        row
        for row in saamg_rows
        if row["solver"] == "saamg" and row["preconditioner"] == "none"
    ]

    assert saamg["include_saamg"] is True
    assert default_saamg_rows
    assert any((row.get("rocalution_stats") or {}).get("amg_num_levels", -1) >= 2 for row in default_saamg_rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in default_saamg_rows)


def test_streamed_large_ras_probe_records_interface_operator_counterevidence() -> None:
    assert PRODUCTIZATION_STREAMED_LARGE_RAS_SHELL_PROBE.exists()

    payload = json.loads(PRODUCTIZATION_STREAMED_LARGE_RAS_SHELL_PROBE.read_text(encoding="utf-8"))
    rows = payload["rows"]
    zero_weight_rows = [
        row for row in rows if row["node_block_subdomain_smoother_weight"] == 0.0
    ]
    nonzero_weight_rows = [
        row for row in rows if row["node_block_subdomain_smoother_weight"] > 0.0
    ]

    assert payload["status"] == "partial"
    assert zero_weight_rows
    assert nonzero_weight_rows
    assert all(
        row["node_block_subdomain_smoother_storage_mode"] == "streamed_dense_inverse"
        for row in rows
    )
    assert all(row["node_block_subdomain_smoother_max_width"] >= 4096 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in rows)
    assert min(row["residual_inf_n"] for row in nonzero_weight_rows) > min(
        row["residual_inf_n"] for row in zero_weight_rows
    )


def test_multiplicative_ras_smoke_records_update_mode_counterevidence() -> None:
    assert PRODUCTIZATION_MULTIPLICATIVE_RAS_SHELL_SMOKE.exists()

    payload = json.loads(PRODUCTIZATION_MULTIPLICATIVE_RAS_SHELL_SMOKE.read_text(encoding="utf-8"))
    rows = payload["rows"]
    row_modes = {row["node_block_subdomain_smoother_update_mode"] for row in rows}
    nonzero_rows = [row for row in rows if row["node_block_subdomain_smoother_weight"] > 0.0]

    assert payload["status"] == "partial"
    assert set(payload["probe_contract"]["node_block_subdomain_smoother_update_mode_candidates"]) == {
        "additive",
        "multiplicative",
    }
    assert {"additive", "multiplicative"} <= row_modes
    assert nonzero_rows
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in rows)
    additive_best = min(
        row["residual_inf_n"]
        for row in nonzero_rows
        if row["node_block_subdomain_smoother_update_mode"] == "additive"
    )
    multiplicative_best = min(
        row["residual_inf_n"]
        for row in nonzero_rows
        if row["node_block_subdomain_smoother_update_mode"] == "multiplicative"
    )
    assert multiplicative_best >= additive_best


def test_interface_edge_coarse_probe_records_pair_boundary_counterevidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_COARSE_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_COARSE_SHELL_PROBE.exists()

    smoke = json.loads(PRODUCTIZATION_INTERFACE_EDGE_COARSE_SHELL_SMOKE.read_text(encoding="utf-8"))
    probe = json.loads(PRODUCTIZATION_INTERFACE_EDGE_COARSE_SHELL_PROBE.read_text(encoding="utf-8"))

    smoke_rows = smoke["rows"]
    probe_rows = probe["rows"]
    assert smoke["status"] == "partial"
    assert probe["status"] == "partial"
    assert {row["node_block_coarse_mode"] for row in smoke_rows} == {"interface_edge"}
    assert {row["node_block_coarse_mode"] for row in probe_rows} == {"interface_edge"}
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in smoke_rows)
    assert all(row["node_block_coarse_column_count"] > 0 for row in smoke_rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in smoke_rows + probe_rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in smoke_rows + probe_rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in smoke_rows + probe_rows)

    smoke_zero = min(row["residual_inf_n"] for row in smoke_rows if row["node_block_coarse_weight"] == 0.0)
    smoke_nonzero = min(row["residual_inf_n"] for row in smoke_rows if row["node_block_coarse_weight"] > 0.0)
    probe_zero = min(row["residual_inf_n"] for row in probe_rows if row["node_block_coarse_weight"] == 0.0)
    probe_nonzero = min(row["residual_inf_n"] for row in probe_rows if row["node_block_coarse_weight"] > 0.0)

    assert smoke_nonzero < smoke_zero
    assert probe_nonzero > probe_zero


def test_interface_edge_smoothed_probe_records_smoothing_boundary() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_SMOOTHED_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_SMOOTHED_SHELL_PROBE.exists()

    smoke = json.loads(PRODUCTIZATION_INTERFACE_EDGE_SMOOTHED_SHELL_SMOKE.read_text(encoding="utf-8"))
    probe = json.loads(PRODUCTIZATION_INTERFACE_EDGE_SMOOTHED_SHELL_PROBE.read_text(encoding="utf-8"))
    smoke_rows = smoke["rows"]
    probe_rows = probe["rows"]

    assert smoke["status"] == "partial"
    assert probe["status"] == "partial"
    assert all(row["node_block_coarse_mode"] == "interface_edge" for row in smoke_rows + probe_rows)
    assert any(row["node_block_coarse_smoothing_applied_steps"] == 1 for row in smoke_rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in smoke_rows + probe_rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in smoke_rows + probe_rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in smoke_rows + probe_rows)

    smoke_unsmoothed = min(
        row["residual_inf_n"]
        for row in smoke_rows
        if row["node_block_coarse_weight"] > 0.0
        and row["node_block_coarse_smoothing_weight"] == 0.0
    )
    smoke_smoothed = min(
        row["residual_inf_n"]
        for row in smoke_rows
        if row["node_block_coarse_weight"] > 0.0
        and row["node_block_coarse_smoothing_weight"] > 0.0
    )
    probe_zero = min(row["residual_inf_n"] for row in probe_rows if row["node_block_coarse_weight"] == 0.0)
    probe_smoothed = min(
        row["residual_inf_n"]
        for row in probe_rows
        if row["node_block_coarse_weight"] > 0.0
        and row["node_block_coarse_smoothing_weight"] > 0.0
    )

    assert smoke_smoothed < smoke_unsmoothed
    assert probe_smoothed > probe_zero


def test_interface_edge_repeated_coarse_probe_records_vcycle_boundary() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_REPEATED_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_REPEATED_SHELL_PROBE.exists()

    smoke = json.loads(PRODUCTIZATION_INTERFACE_EDGE_REPEATED_SHELL_SMOKE.read_text(encoding="utf-8"))
    probe = json.loads(PRODUCTIZATION_INTERFACE_EDGE_REPEATED_SHELL_PROBE.read_text(encoding="utf-8"))
    smoke_rows = smoke["rows"]
    probe_rows = probe["rows"]

    assert smoke["status"] == "partial"
    assert probe["status"] == "partial"
    assert set(smoke["probe_contract"]["node_block_coarse_correction_pass_candidates"]) == {1, 2, 3}
    assert all(row["node_block_coarse_mode"] == "interface_edge" for row in smoke_rows + probe_rows)
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in smoke_rows + probe_rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in smoke_rows + probe_rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in smoke_rows + probe_rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in smoke_rows + probe_rows)

    smoke_zero = min(row["residual_inf_n"] for row in smoke_rows if row["node_block_coarse_weight"] == 0.0)
    smoke_repeated = min(
        row["residual_inf_n"]
        for row in smoke_rows
        if row["node_block_coarse_weight"] > 0.0
        and row["node_block_coarse_correction_passes"] > 1
    )
    probe_zero = min(row["residual_inf_n"] for row in probe_rows if row["node_block_coarse_weight"] == 0.0)
    probe_repeated = min(
        row["residual_inf_n"]
        for row in probe_rows
        if row["node_block_coarse_weight"] > 0.0
        and row["node_block_coarse_correction_passes"] > 1
    )

    assert smoke_repeated < smoke_zero
    assert probe_repeated > probe_zero


def test_interface_edge_rhs_weighted_probe_records_damped_boundary_progress() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_WEIGHTED_SHELL_WEIGHT_SWEEP.exists()

    probe = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_WEIGHTED_SHELL_WEIGHT_SWEEP.read_text(encoding="utf-8")
    )
    rows = probe["rows"]

    assert probe["status"] == "partial"
    assert all(row["node_block_coarse_mode"] == "interface_edge_rhs_weighted" for row in rows)
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in rows)

    zero = min(row["residual_inf_n"] for row in rows if row["node_block_coarse_weight"] == 0.0)
    damped = min(
        row["residual_inf_n"]
        for row in rows
        if 0.0 < row["node_block_coarse_weight"] < 0.01
    )
    full_weight = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_weight"] == 0.01
    )

    assert damped < zero
    assert full_weight > damped


def test_interface_edge_rhs_enriched_probe_records_enrichment_counterevidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_SHELL_WEIGHT_SWEEP.exists()

    probe = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_SHELL_WEIGHT_SWEEP.read_text(encoding="utf-8")
    )
    rows = probe["rows"]

    assert probe["status"] == "partial"
    assert all(row["node_block_coarse_mode"] == "interface_edge_rhs_enriched" for row in rows)
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in rows)

    zero = min(row["residual_inf_n"] for row in rows if row["node_block_coarse_weight"] == 0.0)
    nonzero = min(row["residual_inf_n"] for row in rows if row["node_block_coarse_weight"] > 0.0)
    best_column_count = min(
        row["node_block_coarse_column_count"]
        for row in rows
        if row["residual_inf_n"] == min(candidate["residual_inf_n"] for candidate in rows)
    )

    assert best_column_count > 411
    assert nonzero > zero


def test_interface_edge_rhs_signed_probe_records_magnitude_preference() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_WEIGHTED_SHELL_WEIGHT_SWEEP.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_SIGNED_SHELL_WEIGHT_SWEEP.exists()

    weighted = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_WEIGHTED_SHELL_WEIGHT_SWEEP.read_text(encoding="utf-8")
    )
    signed = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_SIGNED_SHELL_WEIGHT_SWEEP.read_text(encoding="utf-8")
    )
    weighted_rows = weighted["rows"]
    signed_rows = signed["rows"]

    assert signed["status"] == "partial"
    assert all(row["node_block_coarse_mode"] == "interface_edge_rhs_signed" for row in signed_rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in signed_rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in signed_rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in signed_rows)

    weighted_best = min(row["residual_inf_n"] for row in weighted_rows)
    signed_zero = min(row["residual_inf_n"] for row in signed_rows if row["node_block_coarse_weight"] == 0.0)
    signed_best = min(row["residual_inf_n"] for row in signed_rows)
    signed_full_weight = min(
        row["residual_inf_n"]
        for row in signed_rows
        if row["node_block_coarse_weight"] == 0.01
    )

    assert signed_best < signed_zero
    assert weighted_best < signed_best
    assert signed_full_weight > signed_best


def test_interface_edge_rhs_enriched_restricted_probe_records_load_projection_progress() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_WEIGHTED_SHELL_WEIGHT_SWEEP.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_SHELL_WEIGHT_SWEEP.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_WEIGHT_SWEEP.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_FINE_WEIGHT.exists()

    weighted = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_WEIGHTED_SHELL_WEIGHT_SWEEP.read_text(encoding="utf-8")
    )
    enriched = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_SHELL_WEIGHT_SWEEP.read_text(encoding="utf-8")
    )
    restricted = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_WEIGHT_SWEEP.read_text(
            encoding="utf-8"
        )
    )
    fine = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_FINE_WEIGHT.read_text(
            encoding="utf-8"
        )
    )
    weighted_best = min(row["residual_inf_n"] for row in weighted["rows"])
    enriched_best = min(row["residual_inf_n"] for row in enriched["rows"])
    restricted_rows = restricted["rows"]
    fine_rows = fine["rows"]
    restricted_best_row = min(restricted_rows, key=lambda row: row["residual_inf_n"])
    fine_best = min(row["residual_inf_n"] for row in fine_rows)

    assert restricted["status"] == "partial"
    assert fine["status"] == "partial"
    assert restricted_best_row["node_block_coarse_mode"] == "interface_edge_rhs_enriched_restricted"
    assert restricted_best_row["node_block_coarse_load_restriction_applied"] is True
    assert restricted_best_row["node_block_coarse_load_restriction_column_count"] == 411
    assert restricted_best_row["node_block_coarse_column_count"] > 411
    assert restricted_best_row["residual_inf_n"] < weighted_best
    assert restricted_best_row["residual_inf_n"] < enriched_best
    assert fine_best == restricted_best_row["residual_inf_n"]
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in restricted_rows + fine_rows)


def test_interface_edge_rhs_enriched_restricted_coupled_smoke_records_directional_signal() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_SMOKE.exists()

    smoke = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    rows = smoke["rows"]

    assert smoke["status"] == "partial"
    assert smoke["probe_contract"]["matrix_family"] == "coupled_frame_shell_6dof"
    assert all(row["node_block_coarse_mode"] == "interface_edge_rhs_enriched_restricted" for row in rows)
    assert all(row["node_block_coarse_load_restriction_applied"] is True for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert all(row["residual_inf_n"] > row["threshold_n"] for row in rows)

    zero = min(row["residual_inf_n"] for row in rows if row["node_block_coarse_weight"] == 0.0)
    nonzero = min(row["residual_inf_n"] for row in rows if row["node_block_coarse_weight"] > 0.0)

    assert nonzero < zero
    assert nonzero > 5.0e-2


def test_interface_edge_rhs_enriched_restricted_coupled_current_single_underperforms_current_best() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_CURRENT_SINGLE.exists()
    assert PRODUCTIZATION_COUPLING_HOTSPOT_CURRENT_COUPLED.exists()

    current = json.loads(PRODUCTIZATION_COUPLING_HOTSPOT_CURRENT_COUPLED.read_text(encoding="utf-8"))
    restricted = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_CURRENT_SINGLE.read_text(
            encoding="utf-8"
        )
    )
    current_best = min(row["residual_inf_n"] for row in current["rows"])
    restricted_rows = restricted["rows"]
    restricted_best = min(restricted_rows, key=lambda row: row["residual_inf_n"])

    assert restricted["status"] == "partial"
    assert restricted["probe_contract"]["matrix_family"] == "coupled_frame_shell_6dof"
    assert restricted_best["node_block_coarse_mode"] == "interface_edge_rhs_enriched_restricted"
    assert restricted_best["node_block_coarse_load_restriction_applied"] is True
    assert restricted_best["node_block_coarse_load_restriction_column_count"] > 0
    assert restricted_best["device_residency_ratio"] == 1.0
    assert restricted_best["host_dense_solve_fallback_count"] == 0
    assert restricted_best["residual_inf_n"] > restricted_best["threshold_n"]
    assert restricted_best["residual_inf_n"] > current_best


def test_interface_edge_rhs_enriched_orthogonalized_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_ORTHOGONALIZED_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_ORTHOGONALIZED_COUPLED_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_FINE_WEIGHT.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_SMOKE.exists()

    shell = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_ORTHOGONALIZED_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    coupled = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_ORTHOGONALIZED_COUPLED_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    restricted_shell = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_SHELL_FINE_WEIGHT.read_text(
            encoding="utf-8"
        )
    )
    restricted_coupled = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_RHS_ENRICHED_RESTRICTED_COUPLED_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    shell_best = min(shell["rows"], key=lambda row: row["residual_inf_n"])
    coupled_best = min(coupled["rows"], key=lambda row: row["residual_inf_n"])
    restricted_shell_best = min(row["residual_inf_n"] for row in restricted_shell["rows"])
    restricted_coupled_best = min(row["residual_inf_n"] for row in restricted_coupled["rows"])

    assert shell["status"] == "partial"
    assert coupled["status"] == "partial"
    assert shell_best["node_block_coarse_mode"] == "interface_edge_rhs_enriched_orthogonalized"
    assert coupled_best["node_block_coarse_mode"] == "interface_edge_rhs_enriched_orthogonalized"
    assert shell_best["node_block_coarse_load_restriction_applied"] is True
    assert coupled_best["node_block_coarse_load_restriction_applied"] is True
    assert shell_best["node_block_coarse_load_restriction_column_count"] == (
        shell_best["node_block_coarse_column_count"]
    )
    assert coupled_best["node_block_coarse_load_restriction_column_count"] == (
        coupled_best["node_block_coarse_column_count"]
    )
    assert shell_best["host_dense_solve_fallback_count"] == 0
    assert coupled_best["host_dense_solve_fallback_count"] == 0
    assert shell_best["device_residency_ratio"] == 1.0
    assert coupled_best["device_residency_ratio"] == 1.0
    assert shell_best["residual_inf_n"] > restricted_shell_best
    assert coupled_best["residual_inf_n"] > restricted_coupled_best


def test_interface_edge_energy_restricted_shell_smoke_records_basis_quality_signal() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_ENERGY_RESTRICTED_SHELL_SMOKE.exists()

    payload = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_ENERGY_RESTRICTED_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    rows = payload["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    zero = min(row["residual_inf_n"] for row in rows if row["node_block_coarse_weight"] == 0.0)

    assert payload["status"] == "partial"
    assert all(row["node_block_coarse_mode"] == "interface_edge_energy_restricted" for row in rows)
    assert all(row["node_block_coarse_operator"] == "galerkin_ptap" for row in rows)
    assert all(row["node_block_coarse_load_restriction_applied"] is True for row in rows)
    assert all(row["node_block_coarse_energy_mode_count"] > 0 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_coarse_weight"] > 0.0
    assert best["node_block_coarse_correction_passes"] == 3
    assert best["residual_inf_n"] < zero
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_restricted_shell_smoke_records_generalized_basis_signal() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_ENERGY_RESTRICTED_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_RESTRICTED_SHELL_SMOKE.exists()

    energy = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_ENERGY_RESTRICTED_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    geneo = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_RESTRICTED_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    energy_best = min(row["residual_inf_n"] for row in energy["rows"])
    geneo_rows = geneo["rows"]
    geneo_best = min(geneo_rows, key=lambda row: row["residual_inf_n"])
    geneo_zero = min(
        row["residual_inf_n"] for row in geneo_rows if row["node_block_coarse_weight"] == 0.0
    )

    assert geneo["status"] == "partial"
    assert all(row["node_block_coarse_mode"] == "interface_edge_geneo_restricted" for row in geneo_rows)
    assert all(row["node_block_coarse_operator"] == "galerkin_ptap" for row in geneo_rows)
    assert all(row["node_block_coarse_boundary_node_count"] > 0 for row in geneo_rows)
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in geneo_rows)
    assert all(row["node_block_coarse_load_restriction_applied"] is True for row in geneo_rows)
    assert all(row["node_block_coarse_energy_mode_count"] > 0 for row in geneo_rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in geneo_rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in geneo_rows)
    assert geneo_best["node_block_coarse_weight"] > 0.0
    assert geneo_best["node_block_coarse_correction_passes"] == 3
    assert geneo_best["residual_inf_n"] < geneo_zero
    assert geneo_best["residual_inf_n"] < energy_best
    assert geneo_best["residual_inf_n"] > geneo_best["threshold_n"]


def test_interface_edge_geneo_mode_count_sweep_records_basis_width_boundary() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_RESTRICTED_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_MODE_COUNT_SWEEP_SHELL_SMOKE.exists()

    base = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_RESTRICTED_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    sweep = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_MODE_COUNT_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    base_best = min(row["residual_inf_n"] for row in base["rows"])
    rows = sweep["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    by_modes = {
        int(row["node_block_coarse_energy_modes_per_dof"]): row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_weight"] == 0.0025
    }

    assert sweep["status"] == "partial"
    assert sweep["probe_contract"]["node_block_coarse_energy_modes_per_dof_candidates"] == [
        1,
        2,
        3,
        4,
    ]
    assert all(row["node_block_coarse_mode"] == "interface_edge_geneo_restricted" for row in rows)
    assert all(row["node_block_coarse_operator"] == "galerkin_ptap" for row in rows)
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in rows)
    assert all(row["node_block_coarse_energy_mode_count"] > 0 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_coarse_energy_modes_per_dof"] == 3
    assert by_modes[3] < by_modes[2]
    assert by_modes[3] < by_modes[4]
    assert best["residual_inf_n"] < base_best
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_selection_sweep_keeps_low_eigen_best() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_MODE_COUNT_SWEEP_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_SELECTION_SWEEP_SHELL_SMOKE.exists()

    mode_count = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_MODE_COUNT_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    selection = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_SELECTION_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    mode_count_best = min(row["residual_inf_n"] for row in mode_count["rows"])
    rows = selection["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    nonzero_by_selection = {
        row["node_block_coarse_energy_mode_selection"]: row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_weight"] == 0.0025
    }

    assert selection["status"] == "partial"
    assert selection["probe_contract"]["node_block_coarse_energy_mode_selection_candidates"] == [
        "low_eigen",
        "rhs_projection",
        "rhs_energy_score",
    ]
    assert all(row["node_block_coarse_mode"] == "interface_edge_geneo_restricted" for row in rows)
    assert all(row["node_block_coarse_energy_modes_per_dof"] == 3 for row in rows)
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_coarse_energy_mode_selection"] == "low_eigen"
    assert nonzero_by_selection["low_eigen"] == mode_count_best
    assert nonzero_by_selection["rhs_projection"] > nonzero_by_selection["low_eigen"]
    assert nonzero_by_selection["rhs_energy_score"] > nonzero_by_selection["low_eigen"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_weight_pass_sweep_records_single_level_boundary() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_MODE_COUNT_SWEEP_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_WEIGHT_PASS_SWEEP_SHELL_SMOKE.exists()

    mode_count = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_MODE_COUNT_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    weight_pass = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_WEIGHT_PASS_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    mode_count_best = min(row["residual_inf_n"] for row in mode_count["rows"])
    rows = weight_pass["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    large_weight_worst = max(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_weight"] == 0.005
    )

    assert weight_pass["status"] == "partial"
    assert weight_pass["probe_contract"]["node_block_coarse_weight_candidates"] == [
        0.0,
        0.0015,
        0.0025,
        0.0035,
        0.005,
    ]
    assert weight_pass["probe_contract"]["node_block_coarse_correction_pass_candidates"] == [
        1,
        2,
        3,
        4,
        5,
    ]
    assert all(row["node_block_coarse_mode"] == "interface_edge_geneo_restricted" for row in rows)
    assert all(row["node_block_coarse_energy_modes_per_dof"] == 3 for row in rows)
    assert all(row["node_block_coarse_energy_mode_selection"] == "low_eigen" for row in rows)
    assert all(row["node_block_coarse_interface_pair_count"] > 0 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_coarse_weight"] == 0.0015
    assert best["node_block_coarse_correction_passes"] == 5
    assert best["residual_inf_n"] < mode_count_best
    assert mode_count_best - best["residual_inf_n"] < 1.0e-3
    assert large_weight_worst > 26.0
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_schur_cycle_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_WEIGHT_PASS_SWEEP_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_SCHUR_CYCLE_SHELL_SMOKE.exists()

    weight_pass = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_WEIGHT_PASS_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    cycle = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_SCHUR_CYCLE_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    weight_pass_best = min(row["residual_inf_n"] for row in weight_pass["rows"])
    rows = cycle["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    zero_cycle = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_schur_cycle_passes"] == 0
    )
    nonzero_cycle_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_schur_cycle_passes"] > 0
    )

    assert cycle["status"] == "partial"
    assert cycle["probe_contract"]["node_block_coarse_schur_cycle_pass_candidates"] == [
        0,
        1,
        2,
    ]
    assert cycle["probe_contract"]["node_block_coarse_schur_cycle_weight_candidates"] == [
        0.25,
        0.5,
        1.0,
    ]
    assert all(row["node_block_coarse_mode"] == "interface_edge_geneo_restricted" for row in rows)
    assert all(row["node_block_coarse_energy_modes_per_dof"] == 3 for row in rows)
    assert all(row["node_block_coarse_energy_mode_selection"] == "low_eigen" for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_coarse_schur_cycle_passes"] == 0
    assert zero_cycle == weight_pass_best
    assert nonzero_cycle_best > zero_cycle
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_harmonic_extension_records_transfer_boundary() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_WEIGHT_PASS_SWEEP_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_SHELL_SMOKE.exists()

    weight_pass = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_WEIGHT_PASS_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    harmonic = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    weight_pass_best = min(row["residual_inf_n"] for row in weight_pass["rows"])
    rows = harmonic["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    zero_extension = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_harmonic_extension_weight"] == 0.0
    )
    nonzero_extension_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_harmonic_extension_weight"] > 0.0
    )

    assert harmonic["status"] == "partial"
    assert harmonic["probe_contract"][
        "node_block_coarse_harmonic_extension_weight_candidates"
    ] == [0.0, 0.25, 0.5, 1.0]
    assert all(
        row["node_block_coarse_mode"] == "interface_edge_geneo_harmonic_restricted"
        for row in rows
    )
    assert all(row["node_block_coarse_operator"] == "galerkin_ptap" for row in rows)
    assert all(row["node_block_coarse_energy_modes_per_dof"] == 3 for row in rows)
    assert all(row["node_block_coarse_energy_mode_selection"] == "low_eigen" for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert zero_extension == weight_pass_best
    assert nonzero_extension_best < zero_extension
    assert best["node_block_coarse_harmonic_extension_weight"] == 0.5
    assert best["node_block_coarse_harmonic_extension_dof_count"] > 0
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_harmonic_depth_sweep_keeps_one_hop_best() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DEPTH_SHELL_SMOKE.exists()

    harmonic = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    depth = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DEPTH_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    previous_best = min(row["residual_inf_n"] for row in harmonic["rows"])
    rows = depth["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])

    assert depth["status"] == "partial"
    assert depth["probe_contract"][
        "node_block_coarse_harmonic_extension_step_candidates"
    ] == [1, 2, 3]
    assert all(
        row["node_block_coarse_mode"] == "interface_edge_geneo_harmonic_restricted"
        for row in rows
    )
    assert all(row["node_block_coarse_harmonic_extension_weight"] == 0.5 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_coarse_harmonic_extension_steps"] == 1
    assert best["residual_inf_n"] == previous_best
    assert min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_harmonic_extension_steps"] > 1
    ) > best["residual_inf_n"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_harmonic_qr_is_tiny_stabilization_signal() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DEPTH_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.exists()

    depth = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DEPTH_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    qr = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    depth_best = min(row["residual_inf_n"] for row in depth["rows"])
    rows = qr["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    qr_rows = [
        row
        for row in rows
        if row["node_block_coarse_basis_orthogonalization"] == "qr"
    ]
    depth2_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_harmonic_extension_steps"] == 2
    )

    assert qr["status"] == "partial"
    assert qr["probe_contract"][
        "node_block_coarse_basis_orthogonalization_candidates"
    ] == ["none", "qr"]
    assert all(row["node_block_coarse_harmonic_extension_weight"] == 0.5 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert all(row["node_block_coarse_basis_orthogonalization_used"] == "qr" for row in qr_rows)
    assert best["node_block_coarse_basis_orthogonalization"] == "qr"
    assert best["node_block_coarse_harmonic_extension_steps"] == 1
    assert best["residual_inf_n"] < depth_best
    assert depth2_best > best["residual_inf_n"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_harmonic_residual_restriction_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_RESIDUAL_RESTRICTION_SHELL_SMOKE.exists()

    qr = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    restriction = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_RESIDUAL_RESTRICTION_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    qr_best = min(row["residual_inf_n"] for row in qr["rows"])
    rows = restriction["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    residual_target = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_coarse_load_restriction_target"] == "residual"
    )

    assert restriction["status"] == "partial"
    assert restriction["probe_contract"][
        "node_block_coarse_load_restriction_target_candidates"
    ] == ["load", "residual"]
    assert all(row["node_block_coarse_basis_orthogonalization"] == "qr" for row in rows)
    assert all(row["node_block_coarse_harmonic_extension_steps"] == 1 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_coarse_load_restriction_target"] == "load"
    assert best["residual_inf_n"] == qr_best
    assert residual_target > best["residual_inf_n"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_harmonic_dof_filter_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DOF_FILTER_SHELL_SMOKE.exists()

    qr = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    dof_filter = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_DOF_FILTER_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    qr_best = min(row["residual_inf_n"] for row in qr["rows"])
    rows = dof_filter["rows"]
    by_filter = {row["node_block_coarse_local_dof_filter_used"]: row for row in rows}
    best = min(rows, key=lambda row: row["residual_inf_n"])

    assert dof_filter["status"] == "partial"
    assert dof_filter["probe_contract"][
        "node_block_coarse_local_dof_filter_candidates"
    ] == ["all", "translations", "rotations"]
    assert set(by_filter) == {"all", "translations", "rotations"}
    assert all(row["node_block_coarse_mode"] == "interface_edge_geneo_harmonic_restricted" for row in rows)
    assert all(row["node_block_coarse_basis_orthogonalization"] == "qr" for row in rows)
    assert all(row["node_block_coarse_operator"] == "galerkin_ptap" for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert by_filter["translations"]["node_block_coarse_column_count"] < by_filter["all"][
        "node_block_coarse_column_count"
    ]
    assert by_filter["rotations"]["node_block_coarse_column_count"] < by_filter["all"][
        "node_block_coarse_column_count"
    ]
    assert by_filter["translations"]["node_block_coarse_load_restriction_column_count"] < by_filter["all"][
        "node_block_coarse_load_restriction_column_count"
    ]
    assert by_filter["all"]["residual_region_summary"]["translation_dofs"][
        "top64_abs_residual_share"
    ] == 1.0
    assert by_filter["translations"]["residual_inf_n"] > by_filter["all"]["residual_inf_n"]
    assert by_filter["rotations"]["residual_inf_n"] > by_filter["all"]["residual_inf_n"]
    assert best["node_block_coarse_local_dof_filter_used"] == "all"
    assert best["residual_inf_n"] == qr_best
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_edge_geneo_harmonic_energy_orthogonalization_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.exists()
    assert (
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_ENERGY_ORTHOGONALIZATION_SHELL_SMOKE.exists()
    )

    qr = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    energy = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_ENERGY_ORTHOGONALIZATION_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    qr_best = min(row["residual_inf_n"] for row in qr["rows"])
    rows = energy["rows"]
    by_orthogonalization = {
        row["node_block_coarse_basis_orthogonalization"]: row for row in rows
    }
    best = min(rows, key=lambda row: row["residual_inf_n"])

    assert energy["status"] == "partial"
    assert energy["probe_contract"][
        "node_block_coarse_basis_orthogonalization_candidates"
    ] == ["qr", "energy"]
    assert set(by_orthogonalization) == {"qr", "energy"}
    assert all(row["node_block_coarse_mode"] == "interface_edge_geneo_harmonic_restricted" for row in rows)
    assert all(row["node_block_coarse_operator"] == "galerkin_ptap" for row in rows)
    assert all(row["node_block_coarse_local_dof_filter_used"] == "all" for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert by_orthogonalization["energy"][
        "node_block_coarse_basis_orthogonalization_used"
    ] == "energy"
    assert by_orthogonalization["energy"][
        "node_block_coarse_basis_orthogonalization_input_column_count"
    ] == by_orthogonalization["qr"][
        "node_block_coarse_basis_orthogonalization_input_column_count"
    ]
    assert by_orthogonalization["energy"][
        "node_block_coarse_basis_orthogonalization_dropped_column_count"
    ] == 0
    assert by_orthogonalization["energy"]["residual_inf_n"] > by_orthogonalization[
        "qr"
    ]["residual_inf_n"]
    assert best["node_block_coarse_basis_orthogonalization"] == "qr"
    assert best["residual_inf_n"] == qr_best
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_pair_dd_smoother_is_bounded_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_PAIR_DD_SMOOTHER_SHELL_SMOKE.exists()

    qr = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    smoother = json.loads(
        PRODUCTIZATION_INTERFACE_PAIR_DD_SMOOTHER_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    qr_best = min(row["residual_inf_n"] for row in qr["rows"])
    rows = smoother["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    nonzero_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_interface_pair_smoother_weight"] > 0.0
    )

    assert smoother["status"] == "partial"
    assert smoother["probe_contract"][
        "node_block_interface_pair_smoother_weight_candidates"
    ] == [0.0, 0.001, 0.005]
    assert smoother["probe_contract"][
        "node_block_interface_pair_smoother_halo_depth_candidates"
    ] == [0, 1]
    assert all(row["node_block_interface_pair_smoother_block_count"] == 22 for row in rows)
    assert all(row["node_block_interface_pair_smoother_max_width"] == 128 for row in rows)
    assert all(row["node_block_interface_pair_smoother_storage_mode"] == "padded_batched_dense_inverse" for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_interface_pair_smoother_weight"] == 0.0
    assert best["residual_inf_n"] == qr_best
    assert nonzero_best > best["residual_inf_n"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_pair_dd_swept_update_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_PAIR_DD_SWEPT_SHELL_SMOKE.exists()

    qr = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    swept = json.loads(
        PRODUCTIZATION_INTERFACE_PAIR_DD_SWEPT_SHELL_SMOKE.read_text(encoding="utf-8")
    )
    qr_best = min(row["residual_inf_n"] for row in qr["rows"])
    rows = swept["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    nonzero_rows = [
        row for row in rows if row["node_block_interface_pair_smoother_weight"] > 0.0
    ]
    additive_best = min(
        row["residual_inf_n"]
        for row in nonzero_rows
        if row["node_block_interface_pair_smoother_update_mode"] == "additive"
    )
    multiplicative_best = min(
        row["residual_inf_n"]
        for row in nonzero_rows
        if row["node_block_interface_pair_smoother_update_mode"] == "multiplicative"
    )

    assert swept["status"] == "partial"
    assert swept["probe_contract"][
        "node_block_interface_pair_smoother_update_mode_candidates"
    ] == ["additive", "multiplicative"]
    assert {row["node_block_interface_pair_smoother_update_mode"] for row in rows} == {
        "additive",
        "multiplicative",
    }
    assert all(row["node_block_interface_pair_smoother_block_count"] == 22 for row in rows)
    assert all(row["node_block_interface_pair_smoother_max_width"] == 128 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_interface_pair_smoother_weight"] == 0.0
    assert best["residual_inf_n"] == qr_best
    assert multiplicative_best < additive_best
    assert multiplicative_best > best["residual_inf_n"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_pair_dd_coarse_rebalance_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_PAIR_DD_COARSE_REBALANCE_SHELL_SMOKE.exists()

    qr = json.loads(
        PRODUCTIZATION_INTERFACE_EDGE_GENEO_HARMONIC_QR_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    rebalance = json.loads(
        PRODUCTIZATION_INTERFACE_PAIR_DD_COARSE_REBALANCE_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    qr_best = min(row["residual_inf_n"] for row in qr["rows"])
    rows = rebalance["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    no_rebalance_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_interface_pair_coarse_rebalance_passes"] == 0
    )
    rebalance_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_interface_pair_coarse_rebalance_passes"] > 0
    )

    assert rebalance["status"] == "partial"
    assert rebalance["probe_contract"][
        "node_block_interface_pair_coarse_rebalance_pass_candidates"
    ] == [0, 1]
    assert rebalance["probe_contract"][
        "node_block_interface_pair_coarse_rebalance_weight_candidates"
    ] == [0.5]
    assert all(
        row["node_block_interface_pair_smoother_update_mode"] == "multiplicative"
        for row in rows
    )
    assert all(row["node_block_interface_pair_smoother_block_count"] == 22 for row in rows)
    assert all(row["host_dense_solve_fallback_count"] == 0 for row in rows)
    assert all(row["device_residency_ratio"] == 1.0 for row in rows)
    assert best["node_block_interface_pair_smoother_weight"] == 0.0
    assert best["node_block_interface_pair_coarse_rebalance_passes"] == 0
    assert best["residual_inf_n"] == qr_best
    assert no_rebalance_best == best["residual_inf_n"]
    assert rebalance_best > best["residual_inf_n"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_interface_pair_dd_coarse_rebalance_weight_sweep_is_counter_evidence() -> None:
    assert PRODUCTIZATION_INTERFACE_PAIR_DD_SWEPT_SHELL_SMOKE.exists()
    assert PRODUCTIZATION_INTERFACE_PAIR_DD_COARSE_REBALANCE_WEIGHT_SWEEP_SHELL_SMOKE.exists()

    swept = json.loads(
        PRODUCTIZATION_INTERFACE_PAIR_DD_SWEPT_SHELL_SMOKE.read_text(encoding="utf-8")
    )
    sweep = json.loads(
        PRODUCTIZATION_INTERFACE_PAIR_DD_COARSE_REBALANCE_WEIGHT_SWEEP_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    swept_nonzero_best = min(
        row["residual_inf_n"]
        for row in swept["rows"]
        if row["node_block_interface_pair_smoother_weight"] > 0.0
    )
    rows = sweep["rows"]
    best = min(rows, key=lambda row: row["residual_inf_n"])
    no_rebalance_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_interface_pair_coarse_rebalance_passes"] == 0
    )
    rebalance_best = min(
        row["residual_inf_n"]
        for row in rows
        if row["node_block_interface_pair_coarse_rebalance_passes"] > 0
    )

    assert sweep["status"] == "partial"
    assert sweep["probe_contract"][
        "node_block_interface_pair_coarse_rebalance_pass_candidates"
    ] == [0, 1]
    assert sweep["probe_contract"][
        "node_block_interface_pair_coarse_rebalance_weight_candidates"
    ] == [-0.01, -0.001, 0.001, 0.01]
    assert all(
        row["node_block_interface_pair_smoother_weight"] == 0.001 for row in rows
    )
    assert all(
        row["node_block_interface_pair_smoother_update_mode"] == "multiplicative"
        for row in rows
    )
    assert best["node_block_interface_pair_coarse_rebalance_passes"] == 0
    assert best["residual_inf_n"] == swept_nonzero_best
    assert no_rebalance_best == best["residual_inf_n"]
    assert rebalance_best > best["residual_inf_n"]
    assert best["residual_inf_n"] > best["threshold_n"]


def test_rigid_body_restricted_interface_hybrid_coupled_smoke_is_counter_evidence() -> None:
    assert PRODUCTIZATION_RIGID_BODY_CURRENT_COUPLED_SMOKE_BASELINE.exists()
    assert PRODUCTIZATION_RIGID_BODY_RESTRICTED_INTERFACE_HYBRID_COUPLED_SMOKE.exists()
    assert PRODUCTIZATION_RIGID_BODY_RESTRICTED_INTERFACE_HYBRID_COUPLED_TINY_SMOKE.exists()

    baseline = json.loads(
        PRODUCTIZATION_RIGID_BODY_CURRENT_COUPLED_SMOKE_BASELINE.read_text(encoding="utf-8")
    )
    hybrid = json.loads(
        PRODUCTIZATION_RIGID_BODY_RESTRICTED_INTERFACE_HYBRID_COUPLED_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    tiny = json.loads(
        PRODUCTIZATION_RIGID_BODY_RESTRICTED_INTERFACE_HYBRID_COUPLED_TINY_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    baseline_best = min(row["residual_inf_n"] for row in baseline["rows"])
    hybrid_best = min(hybrid["rows"], key=lambda row: row["residual_inf_n"])
    tiny_best = min(tiny["rows"], key=lambda row: row["residual_inf_n"])

    assert baseline["status"] == "partial"
    assert hybrid["status"] == "partial"
    assert tiny["status"] == "partial"
    assert baseline_best == 719.4718284713658
    assert hybrid_best["node_block_coarse_mode"] == "rigid_body"
    assert hybrid_best["node_block_coarse_secondary_mode"] == (
        "interface_edge_rhs_enriched_restricted"
    )
    assert hybrid_best["node_block_coarse_secondary_load_restriction_applied"] is True
    assert hybrid_best["node_block_coarse_secondary_load_restriction_column_count"] == 1628
    assert hybrid_best["node_block_coarse_secondary_column_count"] == 2188
    assert hybrid_best["residual_inf_n"] > baseline_best
    assert tiny_best["node_block_coarse_secondary_weight"] == 0.00025
    assert tiny_best["node_block_coarse_secondary_correction_passes"] == 1
    assert tiny_best["residual_inf_n"] > baseline_best


def test_residual_region_diagnostic_records_galerkin_and_interface_concentration() -> None:
    assert PRODUCTIZATION_RESIDUAL_REGION_DIAGNOSTIC_SHELL_SMOKE.exists()
    payload = json.loads(
        PRODUCTIZATION_RESIDUAL_REGION_DIAGNOSTIC_SHELL_SMOKE.read_text(
            encoding="utf-8"
        )
    )
    best = payload["best_row"]
    summary = best["residual_region_summary"]

    assert payload["status"] == "partial"
    assert best["node_block_coarse_operator"] == "galerkin_ptap"
    assert summary["operator"] == "galerkin_ptap"
    assert best["node_block_coarse_mode"] == "interface_edge_rhs_enriched_restricted"
    assert best["node_block_coarse_load_restriction_applied"] is True
    assert summary["primary_support"]["dof_count"] > 0
    assert summary["primary_support"]["top64_abs_residual_share"] > 0.5
    assert summary["translation_dofs"]["top64_abs_residual_share"] == 1.0
    assert summary["rotation_dofs"]["residual_inf_fraction_of_global"] < 0.5


def test_mgt_rocm_sparse_solver_probe_records_line_gpu_solve(tmp_path: Path) -> None:
    if os.environ.get(RUN_HEAVY_ROCM_TEST_ENV) == "1":
        out = tmp_path / "mgt_rocm_sparse_solver_probe.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts/run_mgt_rocm_sparse_solver_probe.py"),
                "--output-json",
                str(out),
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        payload = json.loads(out.read_text(encoding="utf-8"))
    else:
        assert PRODUCTIZATION_ROCM_RECEIPT.exists(), (
            f"Missing {PRODUCTIZATION_ROCM_RECEIPT}. "
            f"Regenerate it or set {RUN_HEAVY_ROCM_TEST_ENV}=1 to run the GPU probe."
        )
        payload = json.loads(PRODUCTIZATION_ROCM_RECEIPT.read_text(encoding="utf-8"))
    assert payload["generated_at"]
    assert payload["schema_version"] == "mgt-rocm-sparse-solver-probe.v1"
    assert payload["status"] == "ready"
    assert payload["rocm_sparse_solver_probe_ready"] is True
    assert payload["line_frame_rocm_sparse_solver_ready"] is True
    assert payload["full_line_rocm_sparse_equilibrium_ready"] is True
    assert payload["torch_rocm"]["torch_version_hip"]
    line = payload["probe_rows"][0]
    assert line["label"] == "full_line_3dof_elastic"
    assert line["rocm_sparse_cg"]["backend"] == "rocm_torch_sparse_cg"
    assert line["rocm_sparse_cg"]["device_residency_ratio"] == 1.0
    assert line["rocm_sparse_cg"]["relative_residual_inf"] <= 1.0e-8
    assert payload["full_frame_6dof_rocm_sparse_equilibrium_ready"] is True
    assert payload["full_frame_6dof_rocm_sparse_cg_equilibrium_ready"] is False
    assert payload["full_frame_6dof_rocm_component_direct_equilibrium_ready"] is True
    frame = payload["probe_rows"][1]
    assert frame["label"] == "full_frame_6dof_elastic"
    assert frame["rocm_component_dense_direct_ready"] is True
    assert frame["rocm_component_dense_direct"]["backend"] == "rocm_torch_component_dense_direct"
    assert frame["rocm_component_dense_direct"]["relative_residual_inf"] <= 1.0e-8
    assert payload["surface_shell_rocm_sparse_equilibrium_ready"] is True
    assert payload["coupled_frame_shell_rocm_sparse_equilibrium_ready"] is True
    assert payload["surface_shell_rocm_sparse_host_ilu_device_gmres_equilibrium_ready"] is True
    assert payload["coupled_frame_shell_rocm_sparse_host_ilu_device_gmres_equilibrium_ready"] is True
    assert payload["surface_shell_rocm_sparse_cg_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_bicgstab_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_symmetric_scaled_bicgstab_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_block_bicgstab_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_block_gmres_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_node_block_gmres_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_solution_fusion_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_hotspot_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready"] is False
    assert (
        payload[
            "surface_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert payload["surface_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_residual_polishing_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready"] is False
    assert payload["surface_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready"] is False
    assert (
        payload[
            "surface_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert payload["surface_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready"] is False
    assert (
        payload[
            "surface_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "surface_shell_rocm_sparse_schur_interface_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload.get(
            "surface_shell_rocm_sparse_post_schur_residual_row_block_lstsq_refinement_equilibrium_ready",
            False,
        )
        is False
    )
    assert payload["surface_shell_rocm_sparse_spsolve_supported"] is False
    assert payload["coupled_frame_shell_rocm_sparse_cg_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_bicgstab_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_symmetric_scaled_bicgstab_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_block_bicgstab_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_restarted_defect_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_block_gmres_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_node_block_gmres_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_solution_fusion_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_hotspot_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_dof_hotspot_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_wide_dof_hotspot_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_column_lstsq_hotspot_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_direct_column_lstsq_hotspot_correction_equilibrium_ready"] is False
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_compressed_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"
        ]
        is False
    )
    assert payload["coupled_frame_shell_rocm_sparse_row_neighborhood_lstsq_hotspot_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_hotspot_solution_fusion_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_post_hotspot_node_block_gmres_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_post_hotspot_solution_fusion_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_small_component_direct_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_post_hotspot_block_gmres_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_post_small_component_solution_fusion_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_post_fusion_row_neighborhood_lstsq_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_residual_row_kaczmarz_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_residual_polishing_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_large_component_coarse_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_micro_residual_row_kaczmarz_correction_equilibrium_ready"] is False
    assert payload["coupled_frame_shell_rocm_sparse_residual_row_block_lstsq_correction_equilibrium_ready"] is False
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_post_block_lstsq_residual_row_kaczmarz_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_post_kaczmarz_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_post_refinement_residual_row_kaczmarz_polish_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_post_polish_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert payload["coupled_frame_shell_rocm_sparse_post_block_lstsq_solution_fusion_equilibrium_ready"] is False
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_post_fusion_residual_row_block_lstsq_refinement_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_overlapping_schwarz_patch_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_additive_schwarz_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_deflated_jacobi_krylov_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_enriched_structural_node_coarse_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload[
            "coupled_frame_shell_rocm_sparse_schur_interface_correction_equilibrium_ready"
        ]
        is False
    )
    assert (
        payload.get(
            "coupled_frame_shell_rocm_sparse_post_schur_residual_row_block_lstsq_refinement_equilibrium_ready",
            False,
        )
        is False
    )
    assert payload["coupled_frame_shell_rocm_sparse_spsolve_supported"] is False
    assert payload["surface_shell_rocm_sparse_residual_replay_ready"] is True
    assert payload["coupled_frame_shell_rocm_sparse_residual_replay_ready"] is True
    shell = payload["probe_rows"][2]
    shell_solve = payload["probe_rows"][3]
    coupled_solve = payload["probe_rows"][5]
    assert shell["label"] == "surface_shell_bending_rocm_residual_replay"
    assert shell["backend"] == "rocm_torch_sparse_residual_replay"
    assert shell["relative_residual_inf"] <= 5.0e-8
    assert shell_solve["label"] == "surface_shell_bending_rocm_sparse_solve_attempt"
    assert coupled_solve["label"] == "coupled_frame_shell_rocm_sparse_solve_attempt"
    assert shell_solve["ready"] is True
    assert coupled_solve["ready"] is True
    shell_host_ilu = shell_solve["rocm_sparse_host_ilu_device_gmres"]
    coupled_host_ilu = coupled_solve["rocm_sparse_host_ilu_device_gmres"]
    assert shell_host_ilu["backend"] == "rocm_torch_sparse_host_ilu_device_gmres"
    assert shell_host_ilu["converged"] is True
    assert shell_host_ilu["residual_inf_n"] <= 1.0e-3
    assert shell_host_ilu["cpu_solver_fallback_detected"] is False
    assert shell_host_ilu["matvec_backend"] == "rocm_torch_sparse_csr"
    assert coupled_host_ilu["converged"] is True
    assert coupled_host_ilu["residual_inf_n"] <= 5.0e-2
    assert shell_solve["rocm_sparse_block_bicgstab"]["skipped"] is True
    assert coupled_solve["rocm_sparse_block_bicgstab"]["skipped"] is True
    assert shell_solve["rocm_sparse_cg"]["backend"] == "rocm_torch_sparse_cg"
    assert coupled_solve["rocm_sparse_cg"]["backend"] == "rocm_torch_sparse_cg"
    assert coupled_solve["rocm_sparse_spsolve"]["skipped"] is True
