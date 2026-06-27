"""Tests for the non-promoting physical-residual line-search preview (F1).

Hermetic and synthetic: no dependency on untracked ``*.local.json`` evidence or
the long-running solver probe.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest


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
# 1. default operator unchanged
# ---------------------------------------------------------------------------
def test_default_operator_remains_current_normalized():
    preview = _load("run_g1_physical_consistent_line_search_preview")
    payload = preview.run_g1_physical_consistent_line_search_preview(output_json=None)
    assert payload["default_global_newton_operator"] == "current_normalized_frame_geometric"


# ---------------------------------------------------------------------------
# 2. physical line-search excludes solver lambda
# ---------------------------------------------------------------------------
def test_physical_line_search_excludes_lambda():
    preview = _load("run_g1_physical_consistent_line_search_preview")
    payload = preview.run_g1_physical_consistent_line_search_preview(output_json=None)
    assert payload["uses_solver_normalization_lambda"] is False
    assert payload["normalization_lambda_excluded"] is True


# ---------------------------------------------------------------------------
# 3. report is non-promoting even when line-search succeeds
# ---------------------------------------------------------------------------
def test_report_non_promoting_on_success(tmp_path):
    preview = _load("run_g1_physical_consistent_line_search_preview")
    out = tmp_path / "preview.local.json"
    payload = preview.run_g1_physical_consistent_line_search_preview(output_json=out)
    assert payload["line_search_preview"]["status"] == "ready"
    assert payload["is_preview_only"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["claim_boundary"] == "non_promoting_line_search_preview_only"
    flat = repr(payload).lower()
    assert "g1_closure_passed" not in flat
    assert "full_load_closure_passed" not in flat
    assert "direct_residual_newton_ready" not in flat
    assert out.is_file()


# ---------------------------------------------------------------------------
# 4 + 5. accepts alpha > 1.25e-4 and reduction beats 1.9%
# ---------------------------------------------------------------------------
def test_accepts_alpha_above_d_threshold():
    preview = _load("run_g1_physical_consistent_line_search_preview")
    payload = preview.run_g1_physical_consistent_line_search_preview(output_json=None)
    ls = payload["line_search_preview"]
    assert ls["status"] == "ready"
    assert ls["accepted_alpha"] > 1.25e-4
    assert ls["beats_d_tiny_alpha_threshold"] is True


def test_residual_reduction_beats_d_baseline():
    preview = _load("run_g1_physical_consistent_line_search_preview")
    payload = preview.run_g1_physical_consistent_line_search_preview(output_json=None)
    ls = payload["line_search_preview"]
    assert ls["residual_reduction_ratio"] > 0.019
    assert ls["beats_d_residual_reduction_baseline"] is True


# ---------------------------------------------------------------------------
# 6. predicted/actual mismatch improves vs D baseline (~8.3e5)
# ---------------------------------------------------------------------------
def test_mismatch_ratio_improves_vs_d_baseline():
    preview = _load("run_g1_physical_consistent_line_search_preview")
    payload = preview.run_g1_physical_consistent_line_search_preview(output_json=None)
    mr = payload["mismatch_reduction"]
    assert mr["improved"] is True
    assert mr["f_preview_predicted_actual_ratio"] < 1000.0
    assert mr["f_preview_predicted_actual_ratio"] < mr["d_audit_max_predicted_actual_ratio"]


# ---------------------------------------------------------------------------
# 7. no descent -> status no_descent_found, no closure promotion
# ---------------------------------------------------------------------------
def test_no_descent_direction_reports_no_closure():
    ls_mod = _load("g1_physical_residual_line_search")
    rng = np.random.default_rng(3)
    n = 8
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + np.eye(n)
    f = rng.standard_normal(n)

    def residual_fn(u):
        return a @ u - f

    u = rng.standard_normal(n)
    r0 = residual_fn(u)
    # ascent-ish direction: moving along p multiplies the residual, never reduces it
    p = np.linalg.solve(a, r0)  # A p = r0 -> R(u+alpha p) = (1+alpha) r0
    result = ls_mod.physical_residual_backtracking_line_search(residual_fn, u, p)
    assert result["status"] == "no_descent_found"
    assert result["accepted_alpha"] is None
    assert result["residual_reduction_ratio"] == 0.0


# ---------------------------------------------------------------------------
# 8. GMRES nonconvergence -> explicit reason_code
# ---------------------------------------------------------------------------
def test_gmres_nonconvergence_reason_code():
    ls_mod = _load("g1_physical_residual_line_search")
    rng = np.random.default_rng(5)
    n = 64
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + 1.0e-3 * np.eye(n)  # somewhat ill-conditioned
    f = rng.standard_normal(n)

    def residual_fn(u):
        return a @ u - f

    u = rng.standard_normal(n)
    p, meta = ls_mod.solve_physical_newton_direction(
        residual_fn, u, mode="matrix_free_gmres", gmres_maxiter=1
    )
    if meta["converged"]:
        pytest.skip("gmres converged within 1 iteration; cannot assert nonconvergence")
    assert p is None
    assert meta["reason_code"] in {
        "gmres_not_converged_maxiter",
        "gmres_illegal_input_or_breakdown",
        "non_finite_direction",
    }


# ---------------------------------------------------------------------------
# 9. NaN residual -> fail closed, no accepted step
# ---------------------------------------------------------------------------
def test_nan_residual_fails_closed():
    ls_mod = _load("g1_physical_residual_line_search")
    n = 5

    def residual_fn(u):
        out = np.asarray(u, dtype=np.float64).copy()
        out[0] = np.nan
        return out

    u = np.ones(n)
    p, meta = ls_mod.solve_physical_newton_direction(residual_fn, u)
    assert p is None
    assert meta["reason_code"] == "nan_residual_at_base_state"
    # line-search also fails closed when handed a NaN direction/residual
    result = ls_mod.physical_residual_backtracking_line_search(
        residual_fn, u, np.ones(n)
    )
    assert result["status"] == "fail_closed_nan"
    assert result["accepted_alpha"] is None


# ---------------------------------------------------------------------------
# extra: matrix-free and direct direction modes agree
# ---------------------------------------------------------------------------
def test_gmres_and_direct_modes_agree():
    preview = _load("run_g1_physical_consistent_line_search_preview")
    gm = preview.run_g1_physical_consistent_line_search_preview(
        direction_mode="matrix_free_gmres", output_json=None
    )
    di = preview.run_g1_physical_consistent_line_search_preview(
        direction_mode="representative_direct", output_json=None
    )
    assert gm["line_search_preview"]["accepted_alpha"] == pytest.approx(
        di["line_search_preview"]["accepted_alpha"]
    )
