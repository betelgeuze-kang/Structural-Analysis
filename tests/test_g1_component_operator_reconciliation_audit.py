"""Hermetic tests for the F2c component operator reconciliation audit.

Pure-numeric synthetic vectors only: no dependency on a real MGT file.
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


# ---------------------------------------------------------------------------
# 1. cosine helper handles zero vectors safely
# ---------------------------------------------------------------------------
def test_safe_cosine_zero_vector():
    aud = _load("g1_operator_component_audit")
    assert aud.safe_cosine(np.zeros(5), np.ones(5)) == 0.0
    assert aud.safe_cosine(np.ones(5), np.zeros(5)) == 0.0
    assert abs(aud.safe_cosine(np.array([1.0, 0.0]), np.array([1.0, 0.0])) - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# 3. scale-only mismatch -> scale_factor
# ---------------------------------------------------------------------------
def test_scale_only_is_scale_factor():
    aud = _load("g1_operator_component_audit")
    jv = np.array([1.0, 2.0, -3.0, 4.0])
    kv = 7.5 * jv  # aligned, only scaled
    assert aud.classify_mismatch(kv, jv) == aud.CLASSIFY_SCALE_FACTOR


def test_identical_is_consistent():
    aud = _load("g1_operator_component_audit")
    jv = np.array([1.0, 2.0, -3.0, 4.0])
    assert aud.classify_mismatch(jv.copy(), jv) == aud.CLASSIFY_CONSISTENT


# ---------------------------------------------------------------------------
# 4. orthogonal mismatch -> decorrelated_not_scale_factor
# ---------------------------------------------------------------------------
def test_orthogonal_is_decorrelated():
    aud = _load("g1_operator_component_audit")
    jv = np.array([1.0, 0.0, 0.0, 0.0])
    kv = np.array([0.0, 1.0, 0.0, 0.0]) * 5.0  # orthogonal
    assert aud.classify_mismatch(kv, jv) == aud.CLASSIFY_DECORRELATED


# ---------------------------------------------------------------------------
# 2. ranked suspects: largest-contribution component first
# ---------------------------------------------------------------------------
def test_rank_suspects_orders_by_contribution():
    aud = _load("g1_operator_component_audit")
    ref = np.array([100.0, 0.0, 0.0])
    actions = {
        "frame": np.array([99.0, 0.0, 0.0]),
        "shell": np.array([1.0, 0.0, 0.0]),
        "spring": np.array([0.0, 0.0, 0.0]),
    }
    rows = aud.component_rows(actions, ref)
    suspects = aud.rank_suspects(rows, parity_pass=False)
    assert suspects[0]["component"] == "frame"
    assert suspects[0]["priority"] == 1
    assert suspects[1]["component"] == "shell"


# ---------------------------------------------------------------------------
# 8. ranked suspects empty only when parity passes
# ---------------------------------------------------------------------------
def test_rank_suspects_empty_when_parity_pass():
    aud = _load("g1_operator_component_audit")
    ref = np.array([1.0, 2.0])
    rows = aud.component_rows({"frame": np.array([1.0, 2.0])}, ref)
    assert aud.rank_suspects(rows, parity_pass=True) == []
    assert len(aud.rank_suspects(rows, parity_pass=False)) >= 1


# ---------------------------------------------------------------------------
# 6. missing component -> present=false, no crash
# ---------------------------------------------------------------------------
def test_missing_component_present_false():
    aud = _load("g1_operator_component_audit")
    ref = np.array([1.0, 2.0, 3.0])
    rows = aud.component_rows({"frame": None, "shell": np.array([1.0, 2.0, 3.0])}, ref)
    frame_row = next(r for r in rows if r["component"] == "frame")
    assert frame_row["present"] is False


# ---------------------------------------------------------------------------
# 7. shape mismatch -> ERR_COMPONENT_SHAPE_MISMATCH
# ---------------------------------------------------------------------------
def test_component_shape_mismatch_raises():
    aud = _load("g1_operator_component_audit")
    ref = np.array([1.0, 2.0, 3.0])
    try:
        aud.component_rows({"frame": np.array([1.0, 2.0])}, ref)
    except ValueError as exc:
        assert aud.ERR_COMPONENT_SHAPE_MISMATCH in str(exc)
    else:
        raise AssertionError("expected ValueError for shape mismatch")


def test_report_shape_mismatch_fail_closed():
    drv = _load("run_g1_component_operator_reconciliation_audit")
    jphys = np.array([1.0, 2.0, 3.0])
    ktotal = np.array([0.1, 0.2, 0.3])
    payload = drv.build_component_audit_report(
        jphys_v=jphys, ktotal_v=ktotal,
        component_actions={"frame": np.array([1.0, 2.0])},  # wrong shape
    )
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_COMPONENT_SHAPE_MISMATCH"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 5. report always non-promoting; reproduces decorrelation + ranks frame
# ---------------------------------------------------------------------------
def test_report_non_promoting_and_ranks_dominant():
    drv = _load("run_g1_component_operator_reconciliation_audit")
    aud = _load("g1_operator_component_audit")
    n = 6
    rng = np.random.default_rng(0)
    frame = rng.standard_normal(n) * 1.0e3   # dominant physical component
    shell = rng.standard_normal(n) * 1.0e1
    spring = np.zeros(n)
    jphys = frame + shell + spring
    ktotal = rng.standard_normal(n) * 1.0e1   # decorrelated, much smaller
    payload = drv.build_component_audit_report(
        jphys_v=jphys, ktotal_v=ktotal,
        component_actions={"frame": frame, "shell": shell, "spring": spring},
    )
    assert payload["is_audit_only"] is True
    assert payload["promotes_g1_closure"] is False
    assert payload["global_parity"]["diagnosis"] == aud.CLASSIFY_DECORRELATED
    assert payload["ranked_suspects"][0]["component"] == "frame"
    # component JVPs reconstruct the total exactly
    assert payload["component_decomposition_reconstruction"]["sum_component_jvp_vs_total_rel_error"] < 1e-10


def test_report_missing_mgt_fail_closed(tmp_path):
    drv = _load("run_g1_component_operator_reconciliation_audit")
    payload = drv.run_g1_component_operator_reconciliation_audit(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["reason_code"] == drv.ERR_MGT_INPUT_MISSING
    assert payload["promotes_g1_closure"] is False
    assert str(drv.DEFAULT_OUTPUT_JSON).endswith(".local.json")
