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
            assert h["accepted_residual_jvp_contract"]["local_l2_residual_descent"] is True
    assert out["summary"]["monotonic_residual_decrease"] is True
    assert out["summary"]["stop_reason"] == drv.STOP_MAX_STEPS
    assert out["summary"]["total_reduction_ratio"] > 0.0
    assert out["summary"]["directional_residual_jvp_contract"][
        "accepted_directions"
    ]["all_local_l2_residual_descent"] is True


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
    assert out["newton_history"][0]["accepted_residual_jvp_contract"][
        "jvp_plus_residual_relative_inf"
    ] < 1.0e-6
    assert out["newton_history"][0]["accepted_residual_jvp_contract"][
        "negative_residual_alignment_cosine"
    ] > 0.999999
    flat = repr(out).lower()
    assert "g1_closure" not in flat
    assert "promotes_g1_closure" not in flat


def test_direction_solve_contract_decomposes_regularization_vs_jvp():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    n = 5
    a = _spd(n)
    shift = 0.25
    k_reg = a + shift * np.eye(n)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    def component_residual_fn(x):
        x = np.asarray(x, dtype=np.float64)
        return {
            "linear_component": a @ x,
            "zero_component": np.zeros_like(x),
        }

    row_metadata = {
        "free": np.arange(12, 12 + n, dtype=np.int64),
        "node_id": np.asarray([100, 101, 102], dtype=np.int64),
        "dof_per_node": 6,
    }

    def direction_fn(x, r):
        p = np.linalg.solve(k_reg, -np.asarray(r, dtype=np.float64))
        contract, action_meta = drv.regularized_direction_solve_contract(
            a,
            k_reg,
            p,
            r,
            regularization_mode="scalar_shift",
            regularization_mu=shift,
            effective_shift=shift,
            scale_source="absolute",
        )
        return p, {
            "reason_code": "ok",
            "direction_solve_contract": contract,
            "_row_metadata": row_metadata,
            "_component_residual_fn": component_residual_fn,
            "_tangent_component_actions": {
                "linear_component": a @ p,
                "zero_component": np.zeros_like(p),
            },
            **action_meta,
        }

    out = drv.run_multistep_newton(
        residual_fn,
        np.zeros(n),
        direction_fn,
        max_newton_steps=1,
        residual_gate_n=1e-12,
    )

    row = out["newton_history"][0]
    contract = row["direction_solve_contract"]
    assert contract["regularized_linear_solve_relative_inf"] < 1.0e-12
    assert contract["jvp_minus_unregularized_tangent_action_relative_inf"] < 1.0e-8
    assert contract["unregularized_tangent_plus_residual_relative_inf"] > 0.0
    assert contract["diagnostic_row_space"] == (
        "free_reduced_dof_index_with_global_dof_mapping"
    )
    assert contract["dominant_jvp_minus_unregularized_tangent_action_rows"]
    first_gap_row = contract["dominant_jvp_minus_unregularized_tangent_action_rows"][0]
    assert "global_dof" in first_gap_row
    assert "node_id" in first_gap_row
    assert first_gap_row["dof_label"] in drv.DOF_LABELS
    component_breakdown = contract["dominant_jvp_gap_component_breakdown"]
    assert component_breakdown["status"] == "ready"
    assert component_breakdown["component_names"] == [
        "linear_component",
        "zero_component",
    ]
    assert component_breakdown["rows"][0]["dominant_component"] == "linear_component"
    assert component_breakdown["rows"][0]["dominant_component_tangent_gap"] in {
        "linear_component",
        "zero_component",
    }
    assert abs(
        component_breakdown["rows"][0]["dominant_component_tangent_gap_value"]
    ) < 1.0e-8
    assert abs(component_breakdown["rows"][0]["component_sum_minus_total_jvp"]) < 1e-8
    assert contract["dominant_unregularized_tangent_plus_residual_rows"]
    assert contract["dominant_regularization_action_rows"]
    assert abs(
        contract["unregularized_tangent_plus_residual_relative_inf"]
        - contract["regularization_action_vs_residual_inf"]
    ) < 1.0e-12
    summary = out["summary"]["directional_residual_jvp_contract"][
        "direction_solve_contracts"
    ]
    assert summary["count"] == 1
    assert summary["max_regularized_linear_solve_relative_inf"] < 1.0e-12
    assert summary["dominant_jvp_gap_row_set"][
        "diagnostic_row_space"
    ] == "free_reduced_dof_index_with_global_dof_mapping"
    assert summary["dominant_jvp_gap_row_set"][
        "dominant_jvp_minus_unregularized_tangent_action_rows"
    ]
    assert summary["dominant_jvp_gap_row_set"][
        "dominant_jvp_gap_component_breakdown"
    ]["rows"][0]["dominant_component"] == "linear_component"


def test_multistep_can_return_final_state_without_changing_default():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    n = 4
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    lu_a = np.linalg.inv(a)

    def direction_fn(x, r):
        return -lu_a @ r, {"reason_code": "ok"}

    default = drv.run_multistep_newton(
        residual_fn, np.zeros(n), direction_fn, max_newton_steps=2
    )
    with_state = drv.run_multistep_newton(
        residual_fn,
        np.zeros(n),
        direction_fn,
        max_newton_steps=2,
        return_final_state=True,
    )
    assert "final_state" not in default
    assert with_state["final_state"].shape == (n,)
    assert np.max(np.abs(residual_fn(with_state["final_state"]))) <= 1.0e-6


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
    assert out["summary"]["signed_direction_globalization_used"] is False
    assert out["summary"]["signed_direction_step_count"] == 0
    assert out["newton_history"][0]["accepted_alpha"] is None
    assert out["newton_history"][0]["reverse_direction_line_search_preview"]["status"] == "ready"
    assert out["newton_history"][0]["forward_residual_jvp_contract"][
        "local_l2_residual_descent"
    ] is False
    assert out["newton_history"][0]["reverse_residual_jvp_contract"][
        "local_l2_residual_descent"
    ] is True


def test_signed_direction_globalization_accepts_reverse_descent_only_when_enabled():
    drv = _load("run_g1_regularized_reference_newton_candidate")
    n = 6
    a = _spd(n)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    def ascent_dir(x, r):
        return np.linalg.solve(a, r), {"reason_code": "ok"}

    default = drv.run_multistep_newton(
        residual_fn,
        np.zeros(n),
        ascent_dir,
        max_newton_steps=5,
        residual_gate_n=1e-12,
    )
    enabled = drv.run_multistep_newton(
        residual_fn,
        np.zeros(n),
        ascent_dir,
        max_newton_steps=5,
        residual_gate_n=1e-12,
        allow_signed_direction_globalization=True,
    )

    assert default["summary"]["stop_reason"] == drv.STOP_NO_DESCENT
    assert enabled["summary"]["residual_gate_passed"] is True
    assert enabled["summary"]["signed_direction_globalization_used"] is True
    assert enabled["summary"]["signed_direction_step_count"] == 1
    first = enabled["newton_history"][0]
    assert first["accepted_direction_sign"] == -1
    assert first["line_search_status"] == "ready_reverse_direction"
    assert first["forward_line_search_status"] == "no_descent_found"
    assert first["reverse_direction_line_search_preview"]["status"] == "ready"
    assert first["forward_residual_jvp_contract"]["local_l2_residual_descent"] is False
    assert first["accepted_residual_jvp_contract"]["local_l2_residual_descent"] is True
    assert first["accepted_residual_jvp_contract"][
        "jvp_plus_residual_relative_inf"
    ] < 1.0e-6


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
