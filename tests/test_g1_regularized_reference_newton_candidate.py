"""Hermetic tests for F2g: regularized reference Newton candidate.

Synthetic systems only: no dependency on a real MGT file.
"""

from __future__ import annotations

import importlib.util
import inspect
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


def _spd(n=8, seed=1):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    return raw @ raw.T + n * np.eye(n)


# ---------------------------------------------------------------------------
# 2 + 3 + 8. accepted step decreases residual; monotonic; max_steps
# ---------------------------------------------------------------------------
def test_multistep_monotonic_decrease_and_max_steps():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    n = 8
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)
    c = 50.0

    def residual_fn(x):
        x = np.asarray(x, dtype=np.float64)
        return a @ x + c * x ** 3 - f  # nonlinear -> modified Newton takes several steps

    lu_a = np.linalg.inv(a)

    def direction_fn(x, r):
        return -lu_a @ r, {"reason_code": "ok"}  # modified Newton with fixed A^-1

    out = drv.run_multistep_newton(
        residual_fn, np.zeros(n), direction_fn, max_newton_steps=6, residual_gate_n=1e-12,
    )
    hist = out["newton_history"]
    assert len(hist) >= 1
    # every recorded accepted step reduced the residual
    for h in hist:
        if h.get("residual_after_n") is not None:
            assert h["residual_after_n"] <= h["residual_before_n"]
    assert out["summary"]["monotonic_residual_decrease"] is True
    assert out["summary"]["stop_reason"] == drv.STOP_MAX_STEPS
    assert out["summary"]["total_reduction_ratio"] > 0.0


# ---------------------------------------------------------------------------
# 4. residual gate pass produces no G1 closure claim
# ---------------------------------------------------------------------------
def test_gate_pass_no_g1_closure():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    n = 6
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f  # linear -> exact Newton in 1 step

    lu_a = np.linalg.inv(a)

    def direction_fn(x, r):
        return -lu_a @ r, {"reason_code": "ok"}

    out = drv.run_multistep_newton(residual_fn, np.zeros(n), direction_fn,
                                   max_newton_steps=5, residual_gate_n=1e-6)
    assert out["summary"]["residual_gate_passed"] is True
    flat = repr(out).lower()
    assert "g1_closure" not in flat
    assert "promotes_g1_closure" not in flat


# ---------------------------------------------------------------------------
# 5. line-search no descent
# ---------------------------------------------------------------------------
def test_line_search_no_descent():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    n = 6
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    def ascent_dir(x, r):
        return np.linalg.solve(a, r), {"reason_code": "ok"}  # +Newton => grows residual

    out = drv.run_multistep_newton(residual_fn, np.zeros(n), ascent_dir,
                                   max_newton_steps=5, residual_gate_n=1e-12)
    assert out["summary"]["stop_reason"] == drv.STOP_NO_DESCENT


# ---------------------------------------------------------------------------
# 6. direction solve failure
# ---------------------------------------------------------------------------
def test_direction_solve_failure():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    n = 5
    a = _spd(n)
    f = np.ones(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    def failing_dir(x, r):
        return None, {"reason_code": "solve_failed"}

    out = drv.run_multistep_newton(residual_fn, np.zeros(n), failing_dir,
                                   max_newton_steps=5, residual_gate_n=1e-12)
    assert out["summary"]["stop_reason"] == drv.STOP_SOLVE_FAILED


# ---------------------------------------------------------------------------
# 7. NaN residual fail-closed
# ---------------------------------------------------------------------------
def test_nan_residual_fail_closed():
    drv = _load("run_g1_regularized_reference_newton_candidate")

    def residual_fn(x):
        out = np.asarray(x, dtype=np.float64).copy()
        out[0] = np.nan
        return out

    def direction_fn(x, r):
        return np.zeros_like(x), {"reason_code": "ok"}

    out = drv.run_multistep_newton(residual_fn, np.ones(4), direction_fn, max_newton_steps=3)
    assert out["summary"]["stop_reason"] == drv.STOP_NAN


# ---------------------------------------------------------------------------
# 1 + 9 + 10. report non-promoting; regularization fields; candidate defaults
# ---------------------------------------------------------------------------
def test_report_non_promoting_and_fields(tmp_path):
    drv = _load("run_g1_regularized_reference_newton_candidate")
    payload = drv.run_g1_regularized_reference_newton_candidate(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["promotes_g1_closure"] is False
    assert payload["is_candidate_only"] is True
    assert payload["reason_code"] == drv.ERR_MGT_INPUT_MISSING
    assert payload["regularization"]["mode"] == "relative_diagonal_shift"
    assert payload["regularization"]["mu"] == 0.1
    assert payload["regularization"]["selected_from_f2f"] is True
    assert payload["claim_boundary"] == "non_promoting_regularized_reference_newton_candidate_only"


def test_candidate_runner_defaults():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    sig = inspect.signature(drv.run_g1_regularized_reference_newton_candidate)
    assert sig.parameters["regularization_mu"].default == 0.1
    assert sig.parameters["regularization_mode"].default == "relative_diagonal_shift"
    assert sig.parameters["frame_service_tangent_source"].default == "real_per_element"
    assert sig.parameters["load_scale"].default == 0.1
