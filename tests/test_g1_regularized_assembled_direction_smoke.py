"""Hermetic tests for F2f: regularized assembled-tangent direction smoke.

Synthetic sparse systems only: no dependency on a real MGT file.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
from scipy.sparse import csr_matrix


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


def _singular_linear(n=8, seed=1):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + n * np.eye(n)
    a[0, :] = 0.0
    a[:, 0] = 0.0  # exact rank deficiency -> singular
    f = rng.standard_normal(n)
    f[0] = 0.0  # keep the null DOF load-free so the rest can reduce

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    return residual_fn, np.zeros(n), csr_matrix(a)


def _spd_linear(n=8, seed=2):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + n * np.eye(n)
    f = rng.standard_normal(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    return residual_fn, np.zeros(n), csr_matrix(a)


# ---------------------------------------------------------------------------
# helper: regularize_matrix
# ---------------------------------------------------------------------------
def test_regularize_scalar_shift():
    reg = _load("g1_regularized_direction")
    k = csr_matrix(np.diag([1.0, 2.0, 3.0]))
    kr, shift, source = reg.regularize_matrix(k, "scalar_shift", 0.5)
    assert shift == 0.5
    assert source == "absolute"
    assert np.allclose(kr.diagonal(), [1.5, 2.5, 3.5])


def test_regularize_relative_diagonal_records_scale():
    reg = _load("g1_regularized_direction")
    k = csr_matrix(np.diag([2.0, 4.0, 6.0]))
    kr, shift, source = reg.regularize_matrix(k, "relative_diagonal_shift", 0.1)
    assert "relative_median_diag" in source
    assert shift == 0.1 * 4.0  # median diag = 4.0


def test_default_regularization_mode_is_none():
    reg = _load("g1_regularized_direction")
    assert reg.DEFAULT_REGULARIZATION_MODE == "none"


# ---------------------------------------------------------------------------
# helper: solve_regularized_direction
# ---------------------------------------------------------------------------
def test_unregularized_singular_fails_closed():
    reg = _load("g1_regularized_direction")
    residual_fn, x0, k = _singular_linear()
    p, meta = reg.solve_regularized_direction(k, residual_fn, x0, mode="none", mu=0.0)
    assert p is None
    assert meta["reason_code"] == reg.ERR_REGULARIZED_SOLVE_FAILED


def test_scalar_shift_makes_singular_solvable():
    reg = _load("g1_regularized_direction")
    residual_fn, x0, k = _singular_linear()
    p, meta = reg.solve_regularized_direction(k, residual_fn, x0, mode="scalar_shift", mu=1.0)
    assert p is not None
    assert meta["factorization_pass"] is True
    assert meta["reason_code"] == reg.PASS


def test_nan_direction_fail_closed(monkeypatch):
    reg = _load("g1_regularized_direction")
    residual_fn, x0, k = _spd_linear()
    monkeypatch.setattr(reg, "spsolve", lambda a, b: np.full(b.shape, np.nan))
    p, meta = reg.solve_regularized_direction(k, residual_fn, x0, mode="scalar_shift", mu=1.0)
    assert p is None
    assert meta["reason_code"] == reg.ERR_REGULARIZED_DIRECTION_NAN


# ---------------------------------------------------------------------------
# sweep core
# ---------------------------------------------------------------------------
def test_report_non_promoting_and_production_lambda_field():
    drv = _load("run_g1_mgt_regularized_assembled_direction_smoke")
    residual_fn, x0, k = _spd_linear()
    payload = drv.run_regularized_sweep_from_closure(
        residual_fn, x0, k, regularization_mode="scalar_shift", sweep=(0.0, 0.1, 1.0),
    )
    assert payload["promotes_g1_closure"] is False
    assert payload["is_smoke_only"] is True
    assert "production_lambda" in payload
    assert payload["claim_boundary"] == "non_promoting_regularized_direction_smoke_only"


def test_unregularized_singular_baseline_recorded():
    drv = _load("run_g1_mgt_regularized_assembled_direction_smoke")
    reg = _load("g1_regularized_direction")
    residual_fn, x0, k = _singular_linear()
    payload = drv.run_regularized_sweep_from_closure(
        residual_fn, x0, k, regularization_mode="scalar_shift", sweep=(0.0, 1.0),
    )
    assert payload["unregularized_baseline"]["factorization_status"] == "singular"
    assert payload["unregularized_baseline"]["reason_code"] == reg.ERR_UNREGULARIZED_TANGENT_SINGULAR


def test_best_candidate_selected_by_reduction():
    drv = _load("run_g1_mgt_regularized_assembled_direction_smoke")
    residual_fn, x0, k = _spd_linear()
    payload = drv.run_regularized_sweep_from_closure(
        residual_fn, x0, k, regularization_mode="scalar_shift", sweep=(0.0, 0.1, 1.0, 10.0),
    )
    best = payload["best_regularized_candidate"]
    assert best is not None
    assert best["selected_by"] == "max_residual_reduction_ratio"
    ready = [r for r in payload["regularization_sweep"]
             if r.get("line_search_status") == "ready" and not r.get("regularization_too_large")]
    assert best["residual_reduction_ratio"] >= max(r["residual_reduction_ratio"] for r in ready)


def test_too_large_regularization_flagged():
    drv = _load("run_g1_mgt_regularized_assembled_direction_smoke")
    residual_fn, x0, k = _spd_linear()
    payload = drv.run_regularized_sweep_from_closure(
        residual_fn, x0, k, regularization_mode="scalar_shift", sweep=(1.0, 1.0e12),
    )
    rows = {r["mu"]: r for r in payload["regularization_sweep"]}
    # a huge scalar shift collapses the direction onto -R (gradient) -> too large
    assert rows[1.0e12].get("regularization_too_large") is True


def test_no_descent_maps_to_review(monkeypatch):
    drv = _load("run_g1_mgt_regularized_assembled_direction_smoke")
    reg = _load("g1_regularized_direction")
    residual_fn, x0, k = _spd_linear()
    r0 = residual_fn(x0)
    ascent = np.linalg.solve(k.toarray(), r0)  # +Newton step => grows residual norm

    def fake_solve(kf, fn, x, *, mode, mu):
        return ascent, {"mode": mode, "mu": float(mu), "effective_shift": float(mu),
                        "scale_source": "absolute", "factorization_pass": True,
                        "reason_code": reg.PASS, "cosine_with_neg_residual": 0.1}

    monkeypatch.setattr(drv, "solve_regularized_direction", fake_solve)
    payload = drv.run_regularized_sweep_from_closure(
        residual_fn, x0, k, regularization_mode="scalar_shift", sweep=(1.0,),
    )
    assert payload["reason_code"] == reg.ERR_LINE_SEARCH_NO_DESCENT
    assert payload["status"] == "review"
    assert payload["promotes_g1_closure"] is False


def test_missing_mgt_input(tmp_path):
    drv = _load("run_g1_mgt_regularized_assembled_direction_smoke")
    payload = drv.run_g1_mgt_regularized_assembled_direction_smoke(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["reason_code"] == drv.ERR_MGT_INPUT_MISSING
    assert payload["promotes_g1_closure"] is False
    assert str(drv.DEFAULT_OUTPUT_JSON).endswith(".local.json")
