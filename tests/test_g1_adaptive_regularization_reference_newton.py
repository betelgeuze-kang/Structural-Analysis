"""Hermetic tests for F2g-3: adaptive regularization reference Newton.

Synthetic systems only: no dependency on a real MGT file.
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


def _spd(n=6, seed=1):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    return raw @ raw.T + n * np.eye(n)


def _linear_closure(n=6, seed=1):
    a = _spd(n, seed)
    f = np.arange(1.0, n + 1.0)

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    return residual_fn, np.zeros(n), a


# ---------------------------------------------------------------------------
# 2. greedy selects the candidate with the lowest post-line-search residual
# ---------------------------------------------------------------------------
def test_greedy_selects_lowest_residual():
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    residual_fn, x0, a = _linear_closure()
    inv = np.linalg.inv(a)
    good = (0.1, lambda r: -inv @ r)              # exact Newton -> residual ~ 0
    weak = (0.001, lambda r: -0.01 * inv @ r)     # tiny damped step -> high residual
    out = drv.run_adaptive_greedy_newton(residual_fn, x0, [good, weak],
                                         max_newton_steps=1, residual_gate_n=1e-12)
    step0 = out["history"][0]
    assert step0["selected_mu"] == 0.1


# ---------------------------------------------------------------------------
# 3. one failing candidate does not kill the step if another works
# ---------------------------------------------------------------------------
def test_failing_candidate_does_not_kill_step():
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    residual_fn, x0, a = _linear_closure()
    inv = np.linalg.inv(a)
    bad = (0.1, lambda r: None)                    # solve failure
    good = (0.01, lambda r: -inv @ r)
    out = drv.run_adaptive_greedy_newton(residual_fn, x0, [bad, good],
                                         max_newton_steps=2, residual_gate_n=1e-9)
    assert out["history"][0]["selected_mu"] == 0.01


# ---------------------------------------------------------------------------
# 4. all candidates fail -> solve_failed
# ---------------------------------------------------------------------------
def test_all_candidates_fail():
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    residual_fn, x0, _a = _linear_closure()
    out = drv.run_adaptive_greedy_newton(residual_fn, x0, [(0.1, lambda r: None)],
                                         max_newton_steps=2)
    assert out["summary"]["stop_reason"] == drv.STOP_SOLVE_FAILED


# ---------------------------------------------------------------------------
# 5. no candidate descent -> no_candidate_descent
# ---------------------------------------------------------------------------
def test_no_candidate_descent():
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    residual_fn, x0, a = _linear_closure()
    inv = np.linalg.inv(a)
    ascent = (0.1, lambda r: inv @ r)              # +Newton -> grows residual
    out = drv.run_adaptive_greedy_newton(residual_fn, x0, [ascent],
                                         max_newton_steps=2, residual_gate_n=1e-12)
    assert out["summary"]["stop_reason"] == drv.STOP_NO_DESCENT


def test_signed_direction_globalization_can_accept_reverse_direction():
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    residual_fn, x0, a = _linear_closure()
    inv = np.linalg.inv(a)
    ascent = (0.1, lambda r: inv @ r)              # forward grows residual
    out = drv.run_adaptive_greedy_newton(
        residual_fn,
        x0,
        [ascent],
        max_newton_steps=2,
        residual_gate_n=1e-6,
        allow_signed_direction_globalization=True,
    )

    assert out["summary"]["residual_gate_passed"] is True
    assert out["history"][0]["line_search_status"] == "ready_reverse_direction"
    assert out["history"][0]["accepted_direction_sign"] == -1


# ---------------------------------------------------------------------------
# 6 + 8 + 9. monotonic + gate pass (no G1) + selected_mu schedule recorded
# ---------------------------------------------------------------------------
def test_monotonic_gate_and_schedule():
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    residual_fn, x0, a = _linear_closure()
    inv = np.linalg.inv(a)
    out = drv.run_adaptive_greedy_newton(residual_fn, x0, [(0.1, lambda r: -inv @ r)],
                                         max_newton_steps=3, residual_gate_n=1e-6)
    assert out["summary"]["residual_gate_passed"] is True
    assert out["summary"]["monotonic_residual_decrease"] is True
    assert out["summary"]["selected_mu_schedule"][0] == 0.1
    assert "g1_closure" not in repr(out).lower()


# ---------------------------------------------------------------------------
# 10. NaN residual -> fail_closed_nan
# ---------------------------------------------------------------------------
def test_nan_residual_fail_closed():
    drv = _load("run_g1_adaptive_regularization_reference_newton")

    def residual_fn(x):
        out = np.asarray(x, dtype=np.float64).copy()
        out[0] = np.nan
        return out

    out = drv.run_adaptive_greedy_newton(residual_fn, np.ones(4),
                                         [(0.1, lambda r: np.zeros_like(r))], max_newton_steps=2)
    assert out["summary"]["stop_reason"] == drv.STOP_NAN


# ---------------------------------------------------------------------------
# 1 + 7. report non-promoting; beats_fixed_mu flag semantics
# ---------------------------------------------------------------------------
def test_report_non_promoting(tmp_path):
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    payload = drv.run_g1_adaptive_regularization_reference_newton(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["promotes_g1_closure"] is False
    assert payload["reason_code"] == drv.ERR_MGT_INPUT_MISSING
    assert payload["adaptive_strategy"]["mode"] == "greedy_per_step_mu_selection"
    assert payload["claim_boundary"] == "non_promoting_adaptive_regularization_reference_candidate_only"
    assert str(drv.DEFAULT_OUTPUT_JSON).endswith(".local.json")


def test_runner_forwards_frame_tangent_and_initial_checkpoint(tmp_path, monkeypatch):
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    n = 4
    a = np.eye(n)
    f = np.arange(1.0, n + 1.0)
    calls: list[dict[str, object]] = []
    loaded: list[Path] = []

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    def fake_closure(**kwargs):
        calls.append(dict(kwargs))
        return residual_fn, np.zeros(n), {
            "tangent_free_csr": csr_matrix(a),
            "free": np.arange(n, dtype=np.int64),
            "dof_count": n,
            "free_dof_count": n,
            "element_count": 1,
            "external_load_inf_n": float(np.max(np.abs(f))),
            "u0": np.zeros(n, dtype=np.float64),
            "frame_tangent_source": kwargs.get("frame_tangent_source"),
            "shell_pressure_load_path_policy": kwargs.get(
                "shell_pressure_load_path_policy"
            ),
        }

    def fake_load_initial_checkpoint_state(**kwargs):
        loaded.append(Path(kwargs["path"]))
        return np.zeros(n), {"path": str(kwargs["path"]), "load_scale": kwargs["load_scale"]}

    monkeypatch.setattr(drv, "build_mgt_physical_residual_closure", fake_closure)
    monkeypatch.setattr(
        drv,
        "_load_initial_checkpoint_state",
        fake_load_initial_checkpoint_state,
    )
    mgt = tmp_path / "fixture.mgt"
    mgt.write_text("*NODE\n", encoding="utf-8")
    checkpoint = tmp_path / "initial.npz"
    checkpoint.write_bytes(b"fixture")
    final_checkpoint = tmp_path / "adaptive.npz"

    payload = drv.run_g1_adaptive_regularization_reference_newton(
        mgt_model=mgt,
        initial_checkpoint_npz=checkpoint,
        frame_tangent_source="force_based_residual_tangent",
        shell_pressure_load_path_policy="attached_components_only",
        regularization_mode="scalar_shift",
        mu_candidates=(0.0,),
        baseline_mu=0.0,
        max_newton_steps=2,
        output_json=tmp_path / "o.json",
        output_final_checkpoint_npz=final_checkpoint,
    )

    assert calls[-1]["frame_tangent_source"] == "force_based_residual_tangent"
    assert calls[-1]["shell_pressure_load_path_policy"] == "attached_components_only"
    assert loaded == [checkpoint]
    assert payload["frame_tangent_source"] == "force_based_residual_tangent"
    assert payload["shell_pressure_load_path_policy"] == "attached_components_only"
    assert payload["initial_state"]["source"] == "checkpoint"
    assert payload["summary"]["residual_gate_passed"] is True
    assert payload["output_final_checkpoint"]["written"] is True
    with np.load(final_checkpoint, allow_pickle=False) as archive:
        assert str(np.asarray(archive["checkpoint_schema"]).item()) == drv.CHECKPOINT_SCHEMA
        assert str(np.asarray(archive["frame_tangent_source"]).item()) == (
            "force_based_residual_tangent"
        )
        assert str(np.asarray(archive["shell_pressure_load_path_policy"]).item()) == (
            "attached_components_only"
        )
        assert bool(np.asarray(archive["adaptive_regularization_candidate_only"]).item()) is True
        assert bool(np.asarray(archive["promotes_g1_closure"]).item()) is False


def test_relinearized_runner_rebuilds_tangent_each_step(tmp_path, monkeypatch):
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    n = 4
    a = np.eye(n)
    f = np.arange(1.0, n + 1.0)
    rebuild_count = 0

    def residual_fn(x):
        return a @ np.asarray(x, dtype=np.float64) - f

    def tangent_rebuild_fn(_x):
        nonlocal rebuild_count
        rebuild_count += 1
        return csr_matrix(a)

    def fake_closure(**_kwargs):
        return residual_fn, np.zeros(n), {
            "tangent_free_csr": csr_matrix(a),
            "tangent_rebuild_fn": tangent_rebuild_fn,
            "free": np.arange(n, dtype=np.int64),
            "dof_count": n,
            "free_dof_count": n,
            "element_count": 1,
            "external_load_inf_n": float(np.max(np.abs(f))),
            "u0": np.zeros(n, dtype=np.float64),
        }

    monkeypatch.setattr(drv, "build_mgt_physical_residual_closure", fake_closure)
    mgt = tmp_path / "fixture.mgt"
    mgt.write_text("*NODE\n", encoding="utf-8")

    payload = drv.run_g1_adaptive_regularization_reference_newton(
        mgt_model=mgt,
        tangent_update_mode=drv.TANGENT_UPDATE_PER_STEP_RELINEARIZED,
        regularization_mode="scalar_shift",
        mu_candidates=(0.0,),
        baseline_mu=0.0,
        max_newton_steps=2,
        output_json=tmp_path / "o.json",
    )

    assert payload["adaptive_strategy"]["tangent_update_mode"] == (
        drv.TANGENT_UPDATE_PER_STEP_RELINEARIZED
    )
    assert payload["summary"]["residual_gate_passed"] is True
    assert payload["history"][0]["tangent_rebuilt"] is True
    assert rebuild_count >= 2  # adaptive + baseline paths both rebuild.


def test_prefactor_skips_singular_mu():
    drv = _load("run_g1_adaptive_regularization_reference_newton")
    from scipy.sparse import csr_matrix
    a = np.eye(5)
    a[0, 0] = 0.0  # singular
    # mode 'none' keeps it singular -> splu fails -> skipped; scalar_shift large -> ok
    solvers = drv._prefactor_mu_solvers(csr_matrix(a), "scalar_shift", (0.0, 1.0))
    mus = [m for m, _ in solvers]
    assert 0.0 not in mus  # singular (no shift) skipped
    assert 1.0 in mus
