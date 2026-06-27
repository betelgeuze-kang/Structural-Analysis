"""Hermetic tests for the F2b-i preconditioned real-MGT line-search smoke.

Synthetic free-space systems only: no dependency on a real MGT file or the heavy
solver stack.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


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


def _diag_closure(diag_values, seed=1):
    d = np.asarray(diag_values, dtype=np.float64)
    rng = np.random.default_rng(seed)
    f = rng.standard_normal(d.size)

    def residual_fn(x):
        return d * np.asarray(x, dtype=np.float64) - f

    return residual_fn, np.zeros(d.size), d.copy()


def _dense_spd_closure(n=10, seed=2):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + n * np.eye(n)
    f = rng.standard_normal(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    return residual_fn, np.zeros(n), np.diag(a).copy()


# ---------------------------------------------------------------------------
# 1 + 2. default preconditioner is none; modes are opt-in
# ---------------------------------------------------------------------------
def test_default_preconditioner_is_none():
    ls = _load("g1_physical_residual_line_search")
    assert ls.DEFAULT_PRECONDITIONER == "none"
    minv, meta = ls.build_jacobi_preconditioner(np.ones(5), "none")
    assert minv is None
    assert meta["mode"] == "none"


def test_preconditioner_modes_opt_in():
    ls = _load("g1_physical_residual_line_search")
    for mode in ("jacobi_diag", "absolute_jacobi_diag", "damped_jacobi_diag"):
        minv, meta = ls.build_jacobi_preconditioner(np.array([1.0, 2.0, 4.0]), mode)
        assert minv is not None
        assert meta["mode"] == mode
        assert meta["applied_in_free_space"] is True


# ---------------------------------------------------------------------------
# 3. Jacobi preconditioner accepts only the free-space vector shape
# ---------------------------------------------------------------------------
def test_preconditioner_shape_enforced():
    ls = _load("g1_physical_residual_line_search")
    minv, _ = ls.build_jacobi_preconditioner(np.array([1.0, 2.0, 3.0]), "absolute_jacobi_diag")
    assert minv(np.ones(3)).shape == (3,)
    try:
        minv(np.ones(4))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError on wrong-size vector")


# ---------------------------------------------------------------------------
# 4. tiny diagonal entries are floored
# ---------------------------------------------------------------------------
def test_tiny_diagonal_floored():
    ls = _load("g1_physical_residual_line_search")
    diag = np.array([1.0e-12, 0.0, 5.0])
    minv, meta = ls.build_jacobi_preconditioner(diag, "absolute_jacobi_diag", floor=1.0e-8)
    assert meta["tiny_diag_count"] == 2
    out = minv(np.ones(3))
    assert np.all(np.isfinite(out))


# ---------------------------------------------------------------------------
# 5. none blocked + preconditioned ready comparison
# ---------------------------------------------------------------------------
def test_none_blocked_preconditioned_ready():
    smoke = _load("run_g1_mgt_preconditioned_physical_line_search_smoke")
    # diagonal system, cond ~1e9: unpreconditioned GMRES with 1 iter cannot converge,
    # but absolute-Jacobi turns M^-1 D into identity -> converges immediately.
    residual_fn, x0, diag = _diag_closure([1.0, 1.0e6, 1.0e-3, 5.0, 2.0e4, 7.0])
    payload = smoke.run_preconditioned_smoke_from_closure(
        residual_fn, x0, diag, preconditioner_mode="absolute_jacobi_diag", gmres_maxiter=1,
    )
    cmp = payload["direction_solve_comparison"]
    assert cmp["none"]["status"] == "blocked"
    assert cmp["absolute_jacobi_diag"]["status"] == "ready"
    assert cmp["absolute_jacobi_diag"]["improved_vs_none"] is True
    assert payload["status"] == "ready"
    assert payload["reason_code"] == smoke.PASS
    assert payload["line_search_preview"]["accepted_alpha"] is not None


# ---------------------------------------------------------------------------
# 6. preconditioned still blocked -> explicit reason_code
# ---------------------------------------------------------------------------
def test_preconditioned_still_blocked_reason_code():
    smoke = _load("run_g1_mgt_preconditioned_physical_line_search_smoke")
    residual_fn, x0, diag = _dense_spd_closure(n=20)
    payload = smoke.run_preconditioned_smoke_from_closure(
        residual_fn, x0, diag, preconditioner_mode="damped_jacobi_diag", gmres_maxiter=1,
    )
    assert payload["status"] in {"blocked", "review"}
    assert payload["reason_code"] == smoke.ERR_DIRECTION_SOLVE_BLOCKED
    pre = payload["direction_solve_comparison"]["damped_jacobi_diag"]
    assert pre["reason_code"] is not None
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 7. line-search no descent -> review, no promotion
# ---------------------------------------------------------------------------
def test_line_search_no_descent(monkeypatch):
    smoke = _load("run_g1_mgt_preconditioned_physical_line_search_smoke")
    residual_fn, x0, diag = _dense_spd_closure(n=8, seed=3)
    # both solves "converge" to an ascent direction -> line-search finds no descent
    a_diag = diag
    r0 = residual_fn(x0)
    ascent = r0 / a_diag  # crude ascent-ish direction in this scaled system

    def fake_solve(fn, x, **kwargs):
        return ascent, {
            "mode": "fake", "converged": True, "reason_code": "ok",
            "iterations": 3, "residual_norm_before": float(np.max(np.abs(r0))),
            "residual_norm_after": 0.0, "preconditioned": bool(kwargs.get("preconditioner_minv")),
        }

    monkeypatch.setattr(smoke, "solve_physical_newton_direction", fake_solve)
    payload = smoke.run_preconditioned_smoke_from_closure(
        residual_fn, x0, diag, preconditioner_mode="absolute_jacobi_diag",
    )
    if payload["reason_code"] == smoke.ERR_LINE_SEARCH_NO_DESCENT:
        assert payload["status"] == "review"
        assert payload["promotes_g1_closure"] is False
    else:
        # if the crude direction happened to descend, it must still be non-promoting
        assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 8. NaN residual -> fail closed
# ---------------------------------------------------------------------------
def test_nan_residual_fail_closed():
    smoke = _load("run_g1_mgt_preconditioned_physical_line_search_smoke")

    def residual_fn(x):
        out = np.asarray(x, dtype=np.float64).copy()
        out[0] = np.nan
        return out

    payload = smoke.run_preconditioned_smoke_from_closure(
        residual_fn, np.ones(5), np.ones(5),
    )
    assert payload["reason_code"] == smoke.ERR_NAN_RESIDUAL
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 9. report always non-promoting; missing MGT input fail-closed
# ---------------------------------------------------------------------------
def test_report_always_non_promoting(tmp_path):
    smoke = _load("run_g1_mgt_preconditioned_physical_line_search_smoke")
    payload = smoke.run_g1_mgt_preconditioned_physical_line_search_smoke(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["reason_code"] == smoke.ERR_MGT_INPUT_MISSING
    assert payload["promotes_g1_closure"] is False
    assert payload["claim_boundary"] == "non_promoting_preconditioned_real_mgt_smoke_only"
    assert str(smoke.DEFAULT_OUTPUT_JSON).endswith(".local.json")
