"""Hermetic tests for the F2b-ii-a assembled-tangent (sparse-direct/ILU) smoke.

Synthetic sparse systems only: no dependency on a real MGT file or the heavy
solver stack.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import csr_matrix, diags


PHASE1 = Path(__file__).resolve().parents[1] / "implementation" / "phase1"


def _load(module_name: str):
    if str(PHASE1) not in sys.path:
        sys.path.insert(0, str(PHASE1))
    path = PHASE1 / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _spd_linear(n=10, seed=1):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + n * np.eye(n)
    f = rng.standard_normal(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    return residual_fn, np.zeros(n), csr_matrix(a)


# ---------------------------------------------------------------------------
# 1 + 2. default solver is matrix-free; direct/ILU are opt-in
# ---------------------------------------------------------------------------
def test_default_direction_solver_is_matrix_free():
    ats = _load("g1_assembled_tangent_solve")
    assert ats.DEFAULT_DIRECTION_SOLVER == "gmres_matrix_free"
    assert "sparse_direct_spsolve" in ats.DIRECTION_SOLVERS
    assert "gmres_ilu" in ats.DIRECTION_SOLVERS


# ---------------------------------------------------------------------------
# 3. assembled tangent shape mismatch
# ---------------------------------------------------------------------------
def test_assembled_tangent_shape_mismatch():
    smoke = _load("run_g1_mgt_sparse_direct_physical_line_search_smoke")
    residual_fn, x0, _a = _spd_linear(n=8)
    wrong_k = csr_matrix(np.eye(6))
    payload = smoke.run_sparse_direct_smoke_from_closure(
        residual_fn, x0, wrong_k, direction_solver="sparse_direct_spsolve",
    )
    assert payload["reason_code"] == "ERR_ASSEMBLED_TANGENT_SHAPE_MISMATCH"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 4. assembled tangent parity failure (K != dR/du)
# ---------------------------------------------------------------------------
def test_assembled_tangent_parity_failure():
    smoke = _load("run_g1_mgt_sparse_direct_physical_line_search_smoke")
    residual_fn, x0, a = _spd_linear(n=10)
    # a deliberately wrong tangent (scaled + shuffled) decorrelated from A
    rng = np.random.default_rng(99)
    bad = csr_matrix(rng.standard_normal((10, 10)))
    payload = smoke.run_sparse_direct_smoke_from_closure(
        residual_fn, x0, bad, direction_solver="sparse_direct_spsolve",
    )
    assert payload["reason_code"] == "ERR_ASSEMBLED_TANGENT_PARITY_FAILED"
    assert payload["status"] == "review"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 5. singular matrix direct solve fails closed
# ---------------------------------------------------------------------------
def test_singular_direct_solve_fails_closed():
    ats = _load("g1_assembled_tangent_solve")
    n = 6
    diag = np.ones(n)
    diag[0] = 0.0  # structurally singular
    k = diags(diag).tocsr()

    def residual_fn(x):
        return np.asarray(x, dtype=np.float64) - 1.0

    p, meta = ats.solve_direction_assembled(k, residual_fn, np.zeros(n), solver="sparse_direct_spsolve")
    assert p is None
    assert meta["reason_code"] in {
        ats.ERR_SPARSE_DIRECT_SOLVE_FAILED, ats.ERR_SPARSE_DIRECT_FACTOR_FAILED,
    }


# ---------------------------------------------------------------------------
# 6. ILU factor failure on a structurally singular matrix
# ---------------------------------------------------------------------------
def test_ilu_factor_failure():
    ats = _load("g1_assembled_tangent_solve")
    n = 6
    k = diags(np.zeros(n)).tocsr()  # all-zero -> ILU cannot factor

    def residual_fn(x):
        return np.asarray(x, dtype=np.float64) - 1.0

    p, meta = ats.solve_direction_assembled(k, residual_fn, np.zeros(n), solver="gmres_ilu")
    assert p is None
    assert meta["reason_code"] == ats.ERR_ILU_FACTOR_FAILED


# ---------------------------------------------------------------------------
# 7. ILU GMRES nonconvergence -> explicit reason code
# ---------------------------------------------------------------------------
def test_ilu_gmres_nonconvergence():
    ats = _load("g1_assembled_tangent_solve")
    rng = np.random.default_rng(5)
    n = 40
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + 1.0e-2 * np.eye(n)
    f = rng.standard_normal(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    # poor ILU (huge drop_tol) + a single iteration: likely will not converge
    p, meta = ats.solve_direction_assembled(
        csr_matrix(a), residual_fn, np.zeros(n), solver="gmres_ilu",
        ilu_drop_tol=0.9, ilu_fill_factor=1.0, gmres_maxiter=1,
    )
    if meta["status"] == "ready":
        import pytest
        pytest.skip("ILU-GMRES converged in 1 iter; cannot assert nonconvergence")
    assert meta["reason_code"] == ats.ERR_ILU_GMRES_NOT_CONVERGED


# ---------------------------------------------------------------------------
# 8. sparse-direct ready -> line-search attempted, non-promoting
# ---------------------------------------------------------------------------
def test_sparse_direct_ready_line_search():
    smoke = _load("run_g1_mgt_sparse_direct_physical_line_search_smoke")
    residual_fn, x0, a = _spd_linear(n=12, seed=4)
    payload = smoke.run_sparse_direct_smoke_from_closure(
        residual_fn, x0, a, direction_solver="sparse_direct_spsolve",
    )
    assert payload["assembled_tangent_parity"]["pass"] is True
    assert payload["status"] == "ready"
    assert payload["reason_code"] == smoke.PASS
    ls = payload["line_search_preview"]
    assert ls["attempted"] is True
    assert ls["accepted_alpha"] is not None
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 9. no descent after solved direction -> review, no promotion
# ---------------------------------------------------------------------------
def test_no_descent_after_solved_direction(monkeypatch):
    smoke = _load("run_g1_mgt_sparse_direct_physical_line_search_smoke")
    residual_fn, x0, a = _spd_linear(n=8, seed=6)
    r0 = residual_fn(x0)
    a_dense = a.toarray()
    ascent = np.linalg.solve(a_dense, r0)  # +Newton step (ascent for residual norm)

    def fake_solve(k, fn, x, **kwargs):
        return ascent, {"solver": kwargs.get("solver", "sparse_direct_spsolve"),
                        "status": "ready", "reason_code": "PASS"}

    monkeypatch.setattr(smoke, "solve_direction_assembled", fake_solve)
    payload = smoke.run_sparse_direct_smoke_from_closure(
        residual_fn, x0, a, direction_solver="sparse_direct_spsolve",
    )
    assert payload["reason_code"] == smoke.ERR_LINE_SEARCH_NO_DESCENT
    assert payload["status"] == "review"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 10. report always non-promoting; missing input fail-closed
# ---------------------------------------------------------------------------
def test_report_always_non_promoting(tmp_path):
    smoke = _load("run_g1_mgt_sparse_direct_physical_line_search_smoke")
    payload = smoke.run_g1_mgt_sparse_direct_physical_line_search_smoke(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["reason_code"] == smoke.ERR_MGT_INPUT_MISSING
    assert payload["promotes_g1_closure"] is False
    assert payload["claim_boundary"] == "non_promoting_sparse_direct_real_mgt_smoke_only"
    assert str(smoke.DEFAULT_OUTPUT_JSON).endswith(".local.json")
