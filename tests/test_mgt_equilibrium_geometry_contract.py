from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_equilibrium_geometry_contract import (  # noqa: E402
    EQUILIBRIUM_GEOMETRY_CONTRACT,
    assembly_node_xyz,
)


def test_assembly_node_xyz_keeps_reference_geometry() -> None:
    node_xyz = np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    u = np.asarray([0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)

    assembly = assembly_node_xyz(node_xyz=node_xyz, u=u)

    np.testing.assert_allclose(assembly, node_xyz)
    assert EQUILIBRIUM_GEOMETRY_CONTRACT == "reference_node_xyz_u_only"
