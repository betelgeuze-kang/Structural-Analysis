"""Hermetic tests for the F2a real-MGT physical line-search smoke.

Synthetic fixtures only: no dependency on a real MGT file or the heavy solver
stack. The real-model closure (``build_mgt_physical_residual_closure``) is
exercised locally, not in these tests.
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


def _spd_linear_closure(n: int = 10, seed: int = 1):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + n * np.eye(n)  # well-conditioned SPD
    f = rng.standard_normal(n)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    return residual_fn, np.zeros(n), a, f


# ---------------------------------------------------------------------------
# 1. missing MGT input -> ERR_MGT_INPUT_MISSING
# ---------------------------------------------------------------------------
def test_missing_mgt_input(tmp_path):
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    out = tmp_path / "s.local.json"
    payload = smoke.run_g1_mgt_physical_line_search_smoke(
        mgt_model=tmp_path / "does_not_exist.mgt", output_json=out
    )
    assert payload["reason_code"] == smoke.ERR_MGT_INPUT_MISSING
    assert payload["status"] == "blocked"
    assert payload["promotes_g1_closure"] is False
    assert out.is_file()


# ---------------------------------------------------------------------------
# 2. smoke report always non-promoting
# ---------------------------------------------------------------------------
def test_report_always_non_promoting():
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    residual_fn, x0, _a, _f = _spd_linear_closure()
    payload = smoke.run_smoke_from_closure(residual_fn, x0, uses_real_mgt_model=False)
    assert payload["is_smoke_only"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["claim_boundary"] == "non_promoting_real_mgt_smoke_only"
    flat = repr(payload).lower()
    assert "g1_closure_passed" not in flat
    assert "full_load_closure_passed" not in flat


# ---------------------------------------------------------------------------
# 3. line-search no descent -> review, no promotion
# ---------------------------------------------------------------------------
def test_no_descent_maps_to_review(monkeypatch):
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    residual_fn, x0, a, _f = _spd_linear_closure()
    r0 = residual_fn(x0)
    # ascent direction: A p = R0 -> R(x0 + alpha p) = (1 + alpha) R0 (strictly grows)
    ascent = np.linalg.solve(a, r0)

    def fake_solve(fn, x, **kwargs):
        return ascent, {"mode": "fake", "converged": True, "reason_code": "ok"}

    monkeypatch.setattr(smoke, "solve_physical_newton_direction", fake_solve)
    payload = smoke.run_smoke_from_closure(residual_fn, x0)
    assert payload["reason_code"] == smoke.ERR_LINE_SEARCH_NO_DESCENT
    assert payload["status"] == "review"
    assert payload["line_search_preview"]["direction_solve"]["mode"] == "fake"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 4. NaN residual -> ERR_NAN_RESIDUAL
# ---------------------------------------------------------------------------
def test_nan_residual():
    smoke = _load("run_g1_mgt_physical_line_search_smoke")

    def residual_fn(x):
        out = np.asarray(x, dtype=np.float64).copy()
        out[0] = np.nan
        return out

    payload = smoke.run_smoke_from_closure(residual_fn, np.ones(6))
    assert payload["reason_code"] == smoke.ERR_NAN_RESIDUAL
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 5. operator shape mismatch -> ERR_OPERATOR_SHAPE_MISMATCH
# ---------------------------------------------------------------------------
def test_operator_shape_mismatch():
    smoke = _load("run_g1_mgt_physical_line_search_smoke")

    def residual_fn(x):
        return np.zeros(np.asarray(x).size + 3)  # wrong-size residual

    payload = smoke.run_smoke_from_closure(residual_fn, np.ones(8))
    assert payload["reason_code"] == smoke.ERR_OPERATOR_SHAPE_MISMATCH
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 6. representative MGT-like SPD fixture accepts alpha > 1.25e-4
# ---------------------------------------------------------------------------
def test_mgt_like_fixture_accepts_alpha(tmp_path):
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    residual_fn, x0, _a, _f = _spd_linear_closure(n=12, seed=2)
    payload = smoke.run_smoke_from_closure(
        residual_fn, x0, uses_real_mgt_model=False, gmres_maxiter=200
    )
    assert payload["status"] == "ready"
    assert payload["reason_code"] == smoke.PASS
    ls = payload["line_search_preview"]
    assert ls["accepted_alpha"] is not None
    assert ls["accepted_alpha"] > 1.25e-4


# ---------------------------------------------------------------------------
# 7. output path ends with .local.json (untracked by .gitignore)
# ---------------------------------------------------------------------------
def test_default_output_is_local_json():
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    assert str(smoke.DEFAULT_OUTPUT_JSON).endswith(".local.json")


# ---------------------------------------------------------------------------
# 8. memory budget guard for dense representative_direct mode
# ---------------------------------------------------------------------------
def test_memory_budget_guard():
    smoke = _load("run_g1_mgt_physical_line_search_smoke")

    def residual_fn(x):
        return np.asarray(x, dtype=np.float64)

    payload = smoke.run_smoke_from_closure(
        residual_fn, np.ones(100), direction_mode="representative_direct",
        free_dof_budget=10,
    )
    assert payload["reason_code"] == smoke.ERR_MEMORY_BUDGET_EXCEEDED
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 9. checkpoint loader accepts direct-residual checkpoint displacement
# ---------------------------------------------------------------------------
def test_checkpoint_loader_accepts_direct_residual_checkpoint(tmp_path):
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    checkpoint = tmp_path / "candidate.npz"
    np.savez(
        checkpoint,
        checkpoint_schema="mgt-direct-residual-newton-state.v1",
        load_scale=np.array(1.0),
        displacement_u=np.array([0.0, 1.5, -2.0], dtype=np.float64),
        direct_residual_inf_n=np.array(0.047),
        residual_gate_passed=np.array(False),
        promotes_g1_closure=np.array(False),
    )

    displacement, meta = smoke._load_checkpoint_displacement(
        checkpoint,
        expected_dof_count=3,
        requested_load_scale=1.0,
    )

    assert displacement.tolist() == [0.0, 1.5, -2.0]
    assert meta["checkpoint_applied"] is True
    assert meta["checkpoint_schema"] == "mgt-direct-residual-newton-state.v1"
    assert meta["checkpoint_load_scale_matches_requested"] is True
    assert meta["checkpoint_direct_residual_inf_n"] == 0.047
    assert meta["checkpoint_residual_gate_passed"] is False
    assert meta["checkpoint_promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 10. checkpoint shape mismatch fails closed before live residual work
# ---------------------------------------------------------------------------
def test_checkpoint_loader_rejects_shape_mismatch(tmp_path):
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    checkpoint = tmp_path / "bad_candidate.npz"
    np.savez(
        checkpoint,
        checkpoint_schema="mgt-direct-residual-newton-state.v1",
        load_scale=np.array(1.0),
        displacement_u=np.array([0.0, 1.0], dtype=np.float64),
    )

    with pytest.raises(ValueError, match="expected DOF count"):
        smoke._load_checkpoint_displacement(
            checkpoint,
            expected_dof_count=3,
            requested_load_scale=1.0,
        )


# ---------------------------------------------------------------------------
# 11. checkpoint provenance is carried by smoke payload resource usage
# ---------------------------------------------------------------------------
def test_smoke_payload_carries_checkpoint_resource_metadata():
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    residual_fn, x0, _a, _f = _spd_linear_closure(n=6, seed=4)
    payload = smoke.run_smoke_from_closure(
        residual_fn,
        x0,
        checkpoint_kind="mgt-direct-residual-newton-state.v1",
        resource_usage={
            "dof_count": 6,
            "node_count": 1,
            "element_count": 1,
            "free_dof_count": 6,
            "peak_memory_mb": None,
            "checkpoint": {
                "checkpoint_applied": True,
                "checkpoint_npz": "candidate.npz",
                "checkpoint_load_scale_matches_requested": True,
            },
        },
    )

    assert payload["checkpoint_kind"] == "mgt-direct-residual-newton-state.v1"
    assert payload["resource_usage"]["checkpoint"]["checkpoint_applied"] is True
    assert payload["resource_usage"]["checkpoint"]["checkpoint_npz"] == "candidate.npz"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 12. blocked direction solve preserves solver metadata
# ---------------------------------------------------------------------------
def test_blocked_direction_solve_preserves_solver_metadata(monkeypatch):
    smoke = _load("run_g1_mgt_physical_line_search_smoke")
    residual_fn, x0, _a, _f = _spd_linear_closure(n=6, seed=6)

    def fake_solve(fn, x, **kwargs):
        return None, {
            "mode": "matrix_free_gmres",
            "converged": False,
            "reason_code": "gmres_not_converged_maxiter",
            "gmres_info": 8,
            "iterations": 8,
        }

    monkeypatch.setattr(smoke, "solve_physical_newton_direction", fake_solve)
    payload = smoke.run_smoke_from_closure(residual_fn, x0)

    assert payload["reason_code"] == smoke.ERR_DIRECTION_SOLVE_BLOCKED
    solve = payload["line_search_preview"]["direction_solve"]
    assert solve["reason_code"] == "gmres_not_converged_maxiter"
    assert solve["gmres_info"] == 8
    assert solve["iterations"] == 8
    assert payload["promotes_g1_closure"] is False
