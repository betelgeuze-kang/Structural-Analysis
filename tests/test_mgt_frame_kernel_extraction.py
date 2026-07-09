from __future__ import annotations

from pathlib import Path

import numpy as np

from structural_analysis.elements.frame3d import (
    FrameProps,
    frame_rotation_matrix,
    local_frame_stiffness,
    rigid_end_offset_transform,
    transform_stiffness,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_mgt_runner_imports_the_product_frame_kernel() -> None:
    source = (
        REPO_ROOT / "implementation/phase1/run_mgt_full_frame_6dof_sparse_equilibrium.py"
    ).read_text(encoding="utf-8")

    assert "from structural_analysis.elements.frame3d import" in source
    assert "local_frame_stiffness as _local_frame_stiffness" in source
    assert "frame_rotation_matrix as _rotation_matrix" in source
    assert "def _local_frame_stiffness(" not in source
    assert "def _rotation_matrix(" not in source
    assert "def _rigid_end_offset_transform(" not in source


def test_shared_frame_kernel_is_symmetric_and_preserves_rigid_offset_mapping() -> None:
    props = FrameProps(
        area_m2=0.02,
        e_n_per_m2=200.0e6,
        g_n_per_m2=200.0e6 / 2.6,
        iy_m4=8.0e-5,
        iz_m4=5.0e-5,
        j_m4=1.0e-5,
    )
    local = local_frame_stiffness(props, 2.0)
    rotation = frame_rotation_matrix(
        np.array([0.0, 0.0, 0.0]),
        np.array([2.0, 0.0, 0.0]),
        roll_deg=30.0,
    )
    global_stiffness = transform_stiffness(local, rotation)
    rigid = rigid_end_offset_transform(
        np.array([0.0, 0.1, 0.0]),
        np.array([0.0, 0.0, 0.1]),
    )
    mapped = rigid.T @ global_stiffness @ rigid

    assert np.allclose(local, local.T, atol=1.0e-12)
    assert np.allclose(mapped, mapped.T, atol=1.0e-8)
    assert np.all(np.isfinite(mapped))
    assert float(np.max(np.abs(mapped))) > 0.0
