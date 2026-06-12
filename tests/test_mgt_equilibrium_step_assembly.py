from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_equilibrium_step_assembly import build_equilibrium_step_assembler  # noqa: E402
from run_mgt_full_frame_6dof_sparse_equilibrium import FrameElement  # noqa: E402


def test_build_equilibrium_step_assembler_freezes_external_load() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [0.0, 0.0, 3.0]], dtype=np.float64)
    elements = [
        FrameElement(
            elem_id=1,
            node_i=0,
            node_j=1,
            section_id=1,
            material_id=1,
            length_m=3.0,
        )
    ]
    section_props = {1: {"A_m2": 0.01, "Iy_m4": 1.0e-4, "Iz_m4": 5.0e-5}}
    material_props = {1: {"E_kN_per_m2": 210000.0, "poisson": 0.3}}
    spring = coo_matrix(
        (np.array([], dtype=np.float64), (np.array([], dtype=np.int64), np.array([], dtype=np.int64))),
        shape=(12, 12),
    ).tocsr()
    assembler, meta = build_equilibrium_step_assembler(
        node_xyz=node_xyz,
        frame_elements=elements,
        elem_type_code=np.asarray([], dtype=np.int32),
        elem_section_id=np.asarray([], dtype=np.int32),
        elem_material_id=np.asarray([], dtype=np.int32),
        conn_ptr=np.asarray([0], dtype=np.int64),
        conn_idx=np.asarray([], dtype=np.int64),
        section_props=section_props,
        material_props=material_props,
        plate_thickness_props={},
        spring_stiffness=spring,
        base_axial_forces={},
        frame_gravity_load_scale=1.0,
        load_scale=0.5,
        restrained={0, 1, 2, 3, 4, 5},
    )
    u = np.zeros(12, dtype=np.float64)
    _k0, f0, _free0, _r0, _rhs0, m0 = assembler(u)
    u[8] = 0.01
    _k1, f1, _free1, _r1, _rhs1, m1 = assembler(u)

    assert meta["frozen_load_scale"] == 0.5
    np.testing.assert_allclose(f0, f1)
    assert m1["frozen_external_load"] is True
