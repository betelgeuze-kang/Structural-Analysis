"""Tests for uncoarsened boundary P-Delta checkpoint contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from run_mgt_uncoarsened_boundary_pdelta_probe import (  # noqa: E402
    CHECKPOINT_SCHEMA_VERSION,
    _annotate_convergence_gates,
    _compact_seed_candidate_row,
    _load_accepted_checkpoint,
    _secant_predict_displacement,
    _write_accepted_checkpoint,
)


def test_uncoarsened_boundary_pdelta_checkpoint_roundtrip(tmp_path: Path) -> None:
    node_id = np.asarray([101, 202], dtype=np.int64)
    displacement = np.arange(12, dtype=np.float64) * 0.01
    step_row = {
        "best_residual_inf_n": 2.5e-5,
        "best_fixed_point_relative_increment": 6.0e-5,
        "final_max_translation_m": 0.42,
    }

    meta = _write_accepted_checkpoint(
        checkpoint_dir=tmp_path,
        load_scale=0.45,
        displacement_u=displacement,
        node_id=node_id,
        step_row=step_row,
    )
    loaded_meta, loaded_u = _load_accepted_checkpoint(
        checkpoint_npz=Path(meta["path"]),
        expected_node_id=node_id,
    )

    assert Path(meta["path"]).is_file()
    assert meta["schema_version"] == CHECKPOINT_SCHEMA_VERSION
    assert loaded_meta["schema_version"] == CHECKPOINT_SCHEMA_VERSION
    assert loaded_meta["load_scale"] == 0.45
    assert loaded_meta["dof_count"] == displacement.size
    assert loaded_meta["node_count"] == node_id.size
    assert loaded_meta["residual_inf_n"] == step_row["best_residual_inf_n"]
    assert loaded_meta["fixed_point_relative_increment"] == step_row[
        "best_fixed_point_relative_increment"
    ]
    np.testing.assert_allclose(loaded_u, displacement)


def test_uncoarsened_boundary_pdelta_checkpoint_rejects_node_mismatch(tmp_path: Path) -> None:
    node_id = np.asarray([101, 202], dtype=np.int64)
    meta = _write_accepted_checkpoint(
        checkpoint_dir=tmp_path,
        load_scale=0.1,
        displacement_u=np.zeros(12, dtype=np.float64),
        node_id=node_id,
        step_row={},
    )

    try:
        _load_accepted_checkpoint(
            checkpoint_npz=Path(meta["path"]),
            expected_node_id=np.asarray([101, 999], dtype=np.int64),
        )
    except ValueError as exc:
        assert "node_id vector does not match" in str(exc)
    else:
        raise AssertionError("mismatched checkpoint node ids should be rejected")


def test_uncoarsened_boundary_pdelta_secant_seed_predicts_target_displacement() -> None:
    previous = np.asarray([0.0, 0.2, -0.4], dtype=np.float64)
    current = np.asarray([0.1, 0.5, -0.1], dtype=np.float64)

    predicted, meta = _secant_predict_displacement(
        previous_load_scale=0.5,
        previous_u=previous,
        current_load_scale=0.6,
        current_u=current,
        target_load_scale=0.65,
    )

    np.testing.assert_allclose(predicted, current + 0.5 * (current - previous))
    assert meta["enabled"] is True
    assert meta["previous_load_scale"] == 0.5
    assert meta["current_load_scale"] == 0.6
    assert meta["target_load_scale"] == 0.65
    assert abs(meta["extrapolation_factor"] - 0.5) <= 1.0e-12
    assert meta["seed_delta_inf_m"] > 0.0


def test_uncoarsened_boundary_pdelta_secant_seed_rejects_shape_mismatch() -> None:
    try:
        _secant_predict_displacement(
            previous_load_scale=0.5,
            previous_u=np.zeros(2, dtype=np.float64),
            current_load_scale=0.6,
            current_u=np.zeros(3, dtype=np.float64),
            target_load_scale=0.65,
        )
    except ValueError as exc:
        assert "displacement shapes do not match" in str(exc)
    else:
        raise AssertionError("mismatched secant checkpoint shapes should be rejected")


def test_uncoarsened_boundary_pdelta_seed_alpha_scan_gate_annotation() -> None:
    row = {
        "equilibrium_replay_residual_inf_n": 2.0e-5,
        "solver_residual_inf_n": 1.0e-4,
        "fixed_point_increment_m": 7.0e-5,
        "fixed_point_relative_increment": 9.0e-5,
        "max_translation_m": 0.75,
        "displacement_cap_exceeded": False,
    }

    _annotate_convergence_gates(
        row,
        residual_tolerance_n=5.0e-4,
        relative_increment_tolerance=1.0e-4,
    )
    compact = _compact_seed_candidate_row(row, alpha=0.25)

    assert row["ready"] is True
    assert row["equilibrium_replay_gate_passed"] is True
    assert row["solver_residual_gate_passed"] is True
    assert compact["alpha"] == 0.25
    assert compact["residual_gate_passed"] is True
    assert compact["equilibrium_replay_gate_passed"] is True
    assert compact["relative_increment_gate_passed"] is True
    assert compact["ready"] is True


def test_uncoarsened_boundary_pdelta_seed_alpha_scan_keeps_increment_gate_strict() -> None:
    row = {
        "equilibrium_replay_residual_inf_n": 2.0e-5,
        "solver_residual_inf_n": 2.0e-5,
        "fixed_point_increment_m": 8.0e-5,
        "fixed_point_relative_increment": 1.2e-4,
        "max_translation_m": 0.75,
        "displacement_cap_exceeded": False,
    }

    _annotate_convergence_gates(
        row,
        residual_tolerance_n=5.0e-4,
        relative_increment_tolerance=1.0e-4,
    )
    compact = _compact_seed_candidate_row(row, alpha=0.5)

    assert row["equilibrium_replay_gate_passed"] is True
    assert row["residual_gate_passed"] is True
    assert row["relative_increment_gate_passed"] is False
    assert row["ready"] is False
    assert compact["ready"] is False


def test_uncoarsened_boundary_pdelta_rejects_solver_only_residual_gate() -> None:
    row = {
        "equilibrium_replay_residual_inf_n": 4.0e-3,
        "solver_residual_inf_n": 2.0e-5,
        "fixed_point_increment_m": 7.0e-5,
        "fixed_point_relative_increment": 9.0e-5,
        "max_translation_m": 0.75,
        "displacement_cap_exceeded": False,
    }

    _annotate_convergence_gates(
        row,
        residual_tolerance_n=5.0e-4,
        relative_increment_tolerance=1.0e-4,
    )

    assert row["solver_residual_gate_passed"] is True
    assert row["equilibrium_replay_gate_passed"] is False
    assert row["residual_gate_passed"] is False
    assert row["ready"] is False
