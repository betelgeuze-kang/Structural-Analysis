from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from mgt_physical_residual_assembly import assemble_physical_residual  # noqa: E402


def test_assemble_physical_residual_matches_linear_equilibrium() -> None:
    stiffness = coo_matrix(([2.0, 2.0], ([0, 1], [0, 1])), shape=(2, 2)).tocsr()
    u = np.asarray([1.0, 2.0], dtype=np.float64)
    f_ext = np.asarray([2.0, 4.0], dtype=np.float64)
    f_int = np.asarray(stiffness @ u, dtype=np.float64)
    free = np.asarray([0, 1], dtype=np.int64)

    residual, rhs = assemble_physical_residual(u=u, f_ext=f_ext, free=free, f_int=f_int)

    np.testing.assert_allclose(residual, np.zeros(2), rtol=0.0, atol=1.0e-12)
    np.testing.assert_allclose(rhs, f_ext)


def test_assemble_physical_residual_reports_nonzero_imbalance() -> None:
    u = np.asarray([0.1], dtype=np.float64)
    f_ext = np.asarray([1.0], dtype=np.float64)
    f_int = np.asarray([0.25], dtype=np.float64)
    free = np.asarray([0], dtype=np.int64)

    residual, _rhs = assemble_physical_residual(u=u, f_ext=f_ext, free=free, f_int=f_int)

    assert float(residual[0]) == -0.75
