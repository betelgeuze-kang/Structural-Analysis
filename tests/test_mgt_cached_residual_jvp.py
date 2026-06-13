from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import diags


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_cached_residual_jvp import (  # noqa: E402
    ResidualJvpBatchCache,
    build_fd_jvp_submatrix,
)
import run_mgt_cached_residual_jvp_batch_probe as batch_probe  # noqa: E402
import run_mgt_cached_residual_jvp_replay_probe as replay_probe  # noqa: E402


def test_cached_residual_jvp_reuses_duplicate_columns() -> None:
    stiffness = diags([2.0, 3.0, 5.0], format="csr")
    free = np.asarray([0, 1, 2], dtype=np.int64)
    base_u = np.asarray([0.5, -0.25, 0.1], dtype=np.float64)
    rhs = np.asarray([1.0, -1.0, 0.0], dtype=np.float64)
    base_residual = np.asarray(stiffness @ base_u, dtype=np.float64) - rhs
    calls = {"residual_only": 0}

    def assemble_residual(
        u: np.ndarray,
        *,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
        external_load_override: np.ndarray | None = None,
        **_kwargs,
    ):
        if residual_only:
            calls["residual_only"] += 1
        f_ext = rhs if external_load_override is None else external_load_override
        free_out = free if free_override is None else free_override
        residual = np.asarray(stiffness @ u, dtype=np.float64)[free_out] - f_ext[free_out]
        return stiffness, f_ext, free_out, residual, f_ext[free_out], {}

    cache = ResidualJvpBatchCache(
        assemble_residual=assemble_residual,
        base_u=base_u,
        base_free=free,
        base_residual=base_residual,
        reference_f_ext=rhs,
    )

    submatrix, rows, summary = build_fd_jvp_submatrix(
        cache=cache,
        free=free,
        target_rows=np.asarray([0, 2], dtype=np.int64),
        support_cols=np.asarray([1, 1], dtype=np.int64),
        epsilon=1.0e-6,
    )

    assert submatrix is not None
    np.testing.assert_allclose(submatrix, np.asarray([[0.0, 0.0], [0.0, 0.0]]))
    assert rows[0]["cache_hit"] is False
    assert rows[1]["cache_hit"] is True
    assert summary["cache_hit_count"] == 1
    assert summary["cache_miss_count"] == 1
    assert calls["residual_only"] == 1


def test_cached_residual_jvp_reports_full_assembly_fallback() -> None:
    stiffness = diags([2.0], format="csr")
    free = np.asarray([0], dtype=np.int64)
    base_u = np.asarray([0.0], dtype=np.float64)
    rhs = np.asarray([0.0], dtype=np.float64)
    base_residual = np.asarray([0.0], dtype=np.float64)

    def assemble_residual(
        u: np.ndarray,
        *,
        residual_only: bool = False,
        external_load_override: np.ndarray | None = None,
        **_kwargs,
    ):
        if residual_only:
            raise TypeError("residual-only unsupported")
        f_ext = rhs if external_load_override is None else external_load_override
        residual = np.asarray(stiffness @ u, dtype=np.float64) - f_ext
        return stiffness, f_ext, free, residual, f_ext, {}

    cache = ResidualJvpBatchCache(
        assemble_residual=assemble_residual,
        base_u=base_u,
        base_free=free,
        base_residual=base_residual,
        reference_f_ext=rhs,
    )

    jvp, row = cache.evaluate_global_dof(global_dof=0, epsilon=1.0e-6)

    assert jvp is not None
    np.testing.assert_allclose(jvp, np.asarray([2.0]))
    assert row["residual_only_assembly"] is False
    assert cache.summary()["full_assembly_count"] == 1


def test_cached_residual_jvp_batch_probe_can_promote_gate_candidate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    stiffness = diags([2.0, 3.0], format="csr")
    free = np.asarray([0, 1], dtype=np.int64)
    base_u = np.asarray([0.1, 0.0], dtype=np.float64)
    rhs = np.asarray([0.0, 0.0], dtype=np.float64)

    def assemble_residual(
        u: np.ndarray,
        *,
        include_component_forces: bool = False,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
        external_load_override: np.ndarray | None = None,
        **_kwargs,
    ):
        f_ext = rhs if external_load_override is None else external_load_override
        free_out = free if free_override is None else free_override
        full_residual = np.asarray(stiffness @ u, dtype=np.float64) - f_ext
        residual = full_residual[free_out]
        meta = {}
        if include_component_forces:
            meta["component_forces"] = {"frame": np.asarray(stiffness @ u, dtype=np.float64)}
        return stiffness, f_ext, free_out, residual, f_ext[free_out], meta

    def build_direct_residual_assembler(**_kwargs):
        return assemble_residual, {"u0": base_u.copy(), "load_scale": 1.0}

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {
                "load_scale": 1.0,
                "path": "fixture.npz",
                "dof_count": 2,
            },
            base_u.copy(),
            None,
            None,
        )

    monkeypatch.setattr(
        batch_probe,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(batch_probe, "_load_checkpoint", load_checkpoint)

    final_checkpoint = tmp_path / "final.npz"
    payload = batch_probe.run_mgt_cached_residual_jvp_batch_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=tmp_path / "probe.json",
        output_npz=tmp_path / "probe.npz",
        output_final_checkpoint_npz=final_checkpoint,
        promote_gate_eligible=True,
        top_residual_count=2,
        max_rows=1,
        component_filter="all",
        selection_policy="top",
        support_columns_per_row=1,
        node_block_support=False,
        max_support_columns=1,
        finite_difference_epsilon_m=1.0e-6,
        alpha_values=(1.0,),
        relative_increment_tolerance=2.0,
    )

    assert payload["promoted_to_final_state"] is True
    assert payload["output_final_checkpoint"]["written"] is True
    assert final_checkpoint.is_file()
    assert payload["best_gate_eligible_candidate"]["direct_residual_inf_n"] < 0.2
    with np.load(final_checkpoint, allow_pickle=False) as archive:
        assert float(np.asarray(archive["direct_residual_inf_n"]).item()) < 0.2


def test_cached_residual_jvp_replay_probe_promotes_saved_correction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    stiffness = diags([2.0, 3.0], format="csr")
    free = np.asarray([0, 1], dtype=np.int64)
    base_u = np.asarray([0.1, 0.0], dtype=np.float64)
    rhs = np.asarray([0.0, 0.0], dtype=np.float64)
    correction_npz = tmp_path / "correction.npz"
    np.savez_compressed(
        correction_npz,
        schema_version=np.asarray("fixture-correction"),
        checkpoint_npz=np.asarray("fixture.npz"),
        target_rows=np.asarray([0], dtype=np.int64),
        support_cols=np.asarray([0], dtype=np.int64),
        correction_u=np.asarray([-0.1, 0.0], dtype=np.float64),
    )

    def assemble_residual(
        u: np.ndarray,
        *,
        residual_only: bool = False,
        free_override: np.ndarray | None = None,
        external_load_override: np.ndarray | None = None,
        **_kwargs,
    ):
        f_ext = rhs if external_load_override is None else external_load_override
        free_out = free if free_override is None else free_override
        full_residual = np.asarray(stiffness @ u, dtype=np.float64) - f_ext
        residual = full_residual[free_out]
        return stiffness, f_ext, free_out, residual, f_ext[free_out], {}

    def build_direct_residual_assembler(**_kwargs):
        return assemble_residual, {"u0": base_u.copy(), "load_scale": 1.0}

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {
                "load_scale": 1.0,
                "path": "fixture.npz",
                "dof_count": 2,
            },
            base_u.copy(),
            None,
            None,
        )

    monkeypatch.setattr(
        replay_probe,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(replay_probe, "_load_checkpoint", load_checkpoint)

    final_checkpoint = tmp_path / "replay_final.npz"
    payload = replay_probe.run_mgt_cached_residual_jvp_replay_probe(
        checkpoint_npz=Path("fixture.npz"),
        correction_npz=correction_npz,
        output_json=tmp_path / "replay.json",
        output_final_checkpoint_npz=final_checkpoint,
        promote_gate_eligible=True,
        alpha_values=(1.0, 0.5),
        relative_increment_tolerance=2.0,
    )

    assert payload["correction_checkpoint_matches_requested"] is True
    assert payload["residual_only_trial_count"] == 2
    assert payload["promoted_to_final_state"] is True
    assert payload["best_gate_eligible_candidate"]["alpha"] == 1.0
    assert final_checkpoint.is_file()
    with np.load(final_checkpoint, allow_pickle=False) as archive:
        assert float(np.asarray(archive["direct_residual_inf_n"]).item()) == 0.0
