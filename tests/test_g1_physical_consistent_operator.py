"""Tests for the opt-in physical-consistent global Newton operator (E, PR 2).

These tests are hermetic and synthetic: they do not depend on untracked
``*.local.json`` evidence or on the long-running solver probe.

They lock the mandatory E success criteria:
  1. the default operator stays the existing normalized path;
  2. the physical operator excludes the solver-only lambda damping;
  3. the operator probe report is non-promoting (no G1 closure field);
  4. the matrix-free JVP matches the physical residual on a small system.
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
# 1. The default operator must remain the existing normalized path.
# ---------------------------------------------------------------------------
def test_default_operator_is_current_normalized():
    op = _load("g1_global_newton_operator")
    assert op.DEFAULT_GLOBAL_NEWTON_OPERATOR == "current_normalized_frame_geometric"
    assert op.normalize_global_newton_operator(None) == "current_normalized_frame_geometric"
    assert op.GLOBAL_NEWTON_OPERATOR_CURRENT == "current_normalized_frame_geometric"


def test_probe_reports_default_operator_unchanged():
    op = _load("g1_global_newton_operator")
    probe = _load("run_g1_physical_consistent_operator_probe")
    payload = probe.run_g1_physical_consistent_operator_probe(output_json=None)
    assert payload["default_global_newton_operator"] == op.GLOBAL_NEWTON_OPERATOR_CURRENT


# ---------------------------------------------------------------------------
# 2. The physical operator excludes the solver-only lambda damping.
# ---------------------------------------------------------------------------
def test_physical_operator_excludes_lambda_damping():
    op = _load("g1_global_newton_operator")
    assert op.operator_uses_solver_normalization_lambda(
        op.GLOBAL_NEWTON_OPERATOR_PHYSICAL
    ) is False
    assert op.operator_uses_solver_normalization_lambda(
        op.GLOBAL_NEWTON_OPERATOR_CURRENT
    ) is True


def test_probe_physical_operator_lambda_flags():
    probe = _load("run_g1_physical_consistent_operator_probe")
    payload = probe.run_g1_physical_consistent_operator_probe(
        global_newton_operator="physical_consistent_frame_shell_material_geometric",
        output_json=None,
    )
    assert payload["uses_solver_normalization_lambda"] is False
    assert payload["normalization_lambda_excluded"] is True


def test_invalid_operator_rejected():
    op = _load("g1_global_newton_operator")
    with pytest.raises(ValueError):
        op.normalize_global_newton_operator("not_a_real_operator")


# ---------------------------------------------------------------------------
# 3. The operator probe report must be non-promoting.
# ---------------------------------------------------------------------------
def test_probe_report_is_non_promoting(tmp_path):
    probe = _load("run_g1_physical_consistent_operator_probe")
    out = tmp_path / "probe.local.json"
    payload = probe.run_g1_physical_consistent_operator_probe(output_json=out)
    assert payload["is_probe_only"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["claim_boundary"] == "non_promoting_operator_probe_only"
    assert payload["line_search_preview"]["status"] == "deferred_to_F"
    # Even though JVP parity passes, there must be NO G1 closure field anywhere.
    assert payload["jvp_parity"]["pass"] is True
    flat = repr(payload).lower()
    assert "g1_closure_passed" not in flat
    assert "direct_residual_newton_ready" not in flat
    assert "full_load_closure_passed" not in flat
    assert out.is_file()


# ---------------------------------------------------------------------------
# 4. The matrix-free JVP matches the physical residual on a small system.
# ---------------------------------------------------------------------------
def test_jvp_matches_linear_system_exactly():
    op = _load("g1_global_newton_operator")
    rng = np.random.default_rng(7)
    n = 12
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + np.eye(n)
    f = rng.standard_normal(n)

    def residual_fn(u):
        return a @ u - f  # physical residual of a linear system; J = a

    u = rng.standard_normal(n)
    v = rng.standard_normal(n)
    jvp = op.physical_consistent_jvp(residual_fn, u, v)
    parity = op.jvp_parity_against_reference(jvp, a @ v)
    assert parity["pass"] is True
    assert parity["max_relative_error"] < 1.0e-8


def test_jvp_matches_nonlinear_system_within_tolerance():
    op = _load("g1_global_newton_operator")
    rng = np.random.default_rng(11)
    n = 10
    raw = rng.standard_normal((n, n))
    a = raw @ raw.T + np.eye(n)
    f = rng.standard_normal(n)
    c = 2.0e3

    def residual_fn(u):
        return a @ u + c * (u ** 3) - f  # J(u) = a + diag(3 c u^2)

    u = 1.0e-3 * rng.standard_normal(n)
    v = rng.standard_normal(n)
    jvp = op.physical_consistent_jvp(residual_fn, u, v)
    analytic = (a + np.diag(3.0 * c * (u ** 2))) @ v
    parity = op.jvp_parity_against_reference(jvp, analytic)
    assert parity["pass"] is True


def test_lambda_free_operator_differs_from_normalized_baseline():
    """The physical operator action must differ from the lambda-damped baseline."""
    probe = _load("run_g1_physical_consistent_operator_probe")
    payload = probe.run_g1_physical_consistent_operator_probe(output_json=None)
    contrast = payload["baseline_operator_contrast"]
    assert contrast["baseline_uses_solver_normalization_lambda"] is True
    # baseline action is materially larger than the physical action (lambda damping).
    assert contrast["baseline_action_over_physical_action_ratio"] > 10.0
    assert payload["jvp_parity"]["pass"] is True
