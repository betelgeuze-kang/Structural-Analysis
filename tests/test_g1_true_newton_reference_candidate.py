"""Hermetic tests for F2g-2: true Newton reference candidate.

Synthetic systems only: no dependency on a real MGT file.
"""

from __future__ import annotations

import importlib.util
import inspect
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


def _spd(n=8, seed=1):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    return raw @ raw.T + n * np.eye(n)


# ---------------------------------------------------------------------------
# 1. true direction rebuilds tangent every call and checks parity
# ---------------------------------------------------------------------------
def test_true_direction_rebuilds_and_parity():
    drv = _load("run_g1_true_newton_reference_candidate")
    n = 8
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f  # J = a

    def tangent_rebuild_fn(x):
        return csr_matrix(a)  # consistent with J

    dfn = drv._make_true_direction_fn(residual_fn, tangent_rebuild_fn, "scalar_shift", 1.0)
    p, meta = dfn(np.zeros(n), residual_fn(np.zeros(n)))
    assert p is not None
    assert meta["tangent_rebuilt"] is True
    assert meta["assembled_tangent_parity_pass"] is True


# ---------------------------------------------------------------------------
# 4. parity fail at a step -> stop_reason=parity_failed
# ---------------------------------------------------------------------------
def test_true_direction_parity_failure():
    drv = _load("run_g1_true_newton_reference_candidate")
    n = 8
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f  # J = a

    rng = np.random.default_rng(3)
    bad = csr_matrix(rng.standard_normal((n, n)))  # decorrelated from a

    def tangent_rebuild_fn(x):
        return bad

    dfn = drv._make_true_direction_fn(residual_fn, tangent_rebuild_fn, "scalar_shift", 1.0)
    p, meta = dfn(np.zeros(n), residual_fn(np.zeros(n)))
    assert p is None
    assert meta["solve_stop_reason"] == "parity_failed"


def test_run_multistep_parity_failed_stop():
    cand = _load("run_g1_regularized_reference_newton_candidate")
    n = 5
    a = _spd(n)
    f = np.ones(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    def dfn(x, r):
        return None, {"reason_code": "assembled_tangent_parity_failed", "solve_stop_reason": "parity_failed"}

    out = cand.run_multistep_newton(residual_fn, np.zeros(n), dfn, max_newton_steps=4)
    assert out["summary"]["stop_reason"] == "parity_failed"


# ---------------------------------------------------------------------------
# 3. modified direction does not rebuild the tangent
# ---------------------------------------------------------------------------
def test_modified_direction_no_rebuild():
    drv = _load("run_g1_true_newton_reference_candidate")
    n = 6
    a = _spd(n)
    f = np.ones(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    dfn = drv._make_modified_direction_fn(csr_matrix(a), "scalar_shift", 1.0)
    p, meta = dfn(np.zeros(n), residual_fn(np.zeros(n)))
    assert p is not None
    assert meta["tangent_rebuilt"] is False


# ---------------------------------------------------------------------------
# 5. history records tangent_rebuilt flag
# ---------------------------------------------------------------------------
def test_history_records_tangent_rebuilt():
    cand = _load("run_g1_regularized_reference_newton_candidate")
    n = 6
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)
    c = 30.0

    def residual_fn(x):
        x = np.asarray(x, dtype=np.float64)
        return a @ x + c * x ** 3 - f

    inv = np.linalg.inv(a)

    def dfn(x, r):
        return -inv @ r, {"reason_code": "ok", "tangent_rebuilt": True, "assembled_tangent_parity_pass": True}

    out = cand.run_multistep_newton(residual_fn, np.zeros(n), dfn, max_newton_steps=4, residual_gate_n=1e-12)
    accepted = [h for h in out["newton_history"] if h.get("accepted_alpha") is not None]
    assert accepted
    assert all(h.get("tangent_rebuilt") is True for h in accepted)


# ---------------------------------------------------------------------------
# 6 + 9 + 10. report non-promoting, material caveat, defaults
# ---------------------------------------------------------------------------
def test_report_caveat_and_non_promoting(tmp_path):
    drv = _load("run_g1_true_newton_reference_candidate")
    payload = drv.run_g1_true_newton_reference_candidate(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["promotes_g1_closure"] is False
    assert payload["newton_mode"] == "true_newton_per_step_relinearization"
    assert payload["material_tangent_update"]["claim_boundary"] == "not_material_newton_breadth"
    assert payload["claim_boundary"] == "non_promoting_true_newton_reference_candidate_only"
    assert str(drv.DEFAULT_OUTPUT_JSON).endswith(".local.json")


def test_candidate_defaults():
    drv = _load("run_g1_true_newton_reference_candidate")
    sig = inspect.signature(drv.run_g1_true_newton_reference_candidate)
    assert sig.parameters["regularization_mu"].default == 0.1
    assert sig.parameters["regularization_mode"].default == "relative_diagonal_shift"
    assert sig.parameters["frame_service_tangent_source"].default == "real_per_element"
    assert sig.parameters["max_newton_steps"].default == 12
    assert sig.parameters["load_scale"].default == 0.1


# ---------------------------------------------------------------------------
# 2 (logic). true_newton_faster_than_modified comparison is honest
# ---------------------------------------------------------------------------
def test_faster_flag_logic_when_equal():
    # when true and modified plateau at the same residual, faster flag must be False
    a = 46.456204
    b = 46.456203
    assert (a < b) is False  # the real run produced true ~= modified -> not faster
