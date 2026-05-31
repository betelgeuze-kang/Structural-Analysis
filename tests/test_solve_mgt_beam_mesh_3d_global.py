#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from solve_mgt_beam_mesh_3d_global import solve_mgt_beam_mesh_3d_global  # noqa: E402


def test_mgt_beam_mesh_3d_linear_tangent_fallback_converges() -> None:
    npz = REPO_ROOT / "implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.npz"
    with np.load(npz, allow_pickle=False) as archive:
        payload = solve_mgt_beam_mesh_3d_global(
            node_xyz=np.asarray(archive["node_xyz"], dtype=np.float64),
            edge_index=np.asarray(archive["edge_index"], dtype=np.int64),
            elem_id=np.asarray(archive["elem_id"], dtype=np.int64),
            elem_type_code=np.asarray(archive["elem_type_code"], dtype=np.int32),
            elem_section_id=np.asarray(archive["elem_section_id"], dtype=np.int32),
            max_elements=120,
            load_scale=1.0,
        )
    assert payload.get("converged") is True
    assert payload.get("solve_mode") in {
        "mgt_npz_beam_mesh_3d_global_newton",
        "mgt_npz_beam_mesh_3d_linear_tangent",
    }
