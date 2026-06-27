"""Hermetic tests for F2e: real per-element service tangent in the MGT closure.

The closure builder itself needs a real MGT file, so these tests cover the
default-source contract (via signatures) and the synthetic analogue of the real
F2e finding: assembled-tangent parity PASS but a singular direct/ILU factorization
that fails closed.
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


# ---------------------------------------------------------------------------
# 1 + 2. real_per_element is the default; placeholder is opt-in
# ---------------------------------------------------------------------------
def test_closure_default_service_tangent_is_real():
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    sig = inspect.signature(smoke.build_mgt_physical_residual_closure)
    assert sig.parameters["frame_service_tangent_source"].default == "real_per_element"


def test_sparse_direct_driver_default_service_tangent_is_real():
    drv = _load("run_g1_mgt_sparse_direct_physical_line_search_smoke")
    sig = inspect.signature(drv.run_g1_mgt_sparse_direct_physical_line_search_smoke)
    assert sig.parameters["frame_service_tangent_source"].default == "real_per_element"


# ---------------------------------------------------------------------------
# 3. parity passes but a singular assembled tangent fails the direct solve
#    (synthetic analogue of the real F2e finding)
# ---------------------------------------------------------------------------
def test_parity_pass_but_singular_direct_fails_closed():
    smoke = _load("run_g1_mgt_sparse_direct_physical_line_search_smoke")
    n = 10
    a = np.eye(n)
    a[0, 0] = 0.0  # singular: zero pivot
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f  # J = a (matches k_free)

    payload = smoke.run_sparse_direct_smoke_from_closure(
        residual_fn, np.zeros(n), csr_matrix(a),
        direction_solver="sparse_direct_spsolve",
    )
    # the assembled tangent matches J (parity pass) but is singular -> fail-closed
    assert payload["assembled_tangent_parity"]["pass"] is True
    assert payload["reason_code"] == "ERR_SPARSE_DIRECT_SOLVE_FAILED"
    assert payload["status"] == "blocked"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 4. CLI exposes both service-tangent sources, default real_per_element
# ---------------------------------------------------------------------------
def test_cli_service_tangent_source_choices():
    src = PHASE1 / "run_g1_mgt_sparse_direct_physical_line_search_smoke.py"
    text = src.read_text(encoding="utf-8")
    assert "--frame-service-tangent-source" in text
    assert "real_per_element" in text
    assert "placeholder_1mpa" in text
