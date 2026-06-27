"""Hermetic tests for the F2d frame operator reconciliation audit.

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
# 2 + 4. scale-only mismatch: classified scale_factor; best scalar fit ~ exact
# ---------------------------------------------------------------------------
def test_scale_only_block_mismatch():
    drv = _load("run_g1_frame_operator_reconciliation_audit")
    jv = np.array([1.0, -2.0, 3.0, 0.5])
    kv = 0.1 * jv  # aligned, scaled down
    m = drv.block_mismatch(kv, jv)
    assert m["classification"] == "scale_factor"
    assert m["scaled_relative_error"] < 1e-9  # best scalar fit recovers J exactly
    assert abs(m["best_scalar_fit"] - 10.0) < 1e-6  # alpha*kv = jv -> alpha=10


# ---------------------------------------------------------------------------
# 3 + 4. decorrelated mismatch: best scalar fit does NOT reduce error
# ---------------------------------------------------------------------------
def test_decorrelated_block_mismatch():
    drv = _load("run_g1_frame_operator_reconciliation_audit")
    jv = np.array([1.0, 0.0, 0.0, 0.0])
    kv = np.array([0.0, 1.0, 0.0, 0.0])
    m = drv.block_mismatch(kv, jv)
    assert m["classification"] == "decorrelated_not_scale_factor"
    assert m["scaled_relative_error"] > 0.5  # scaling cannot fix orthogonality


def test_consistent_block_mismatch():
    drv = _load("run_g1_frame_operator_reconciliation_audit")
    jv = np.array([1.0, -2.0, 3.0])
    m = drv.block_mismatch(jv.copy(), jv)
    assert m["classification"] == "consistent"


# ---------------------------------------------------------------------------
# 5 + 6. report preserves spring/shell non-suspect flags + non-promoting
# ---------------------------------------------------------------------------
def test_report_flags_and_non_promoting():
    drv = _load("run_g1_frame_operator_reconciliation_audit")
    jv = np.array([10.0, 0.0, 0.0])
    blocks = {
        "service_real": {"material": jv.copy(), "geometric_delta": np.zeros(3),
                         "elastic": jv.copy(), "total": jv.copy()},
    }
    payload = drv.build_frame_audit_report(j_frame_v=jv, blocks_by_service=blocks,
                                           frame_share_of_jphys_norm=0.9998)
    assert payload["promotes_g1_closure"] is False
    assert payload["is_audit_only"] is True
    assert payload["global_context"]["spring_is_suspect"] is False
    assert payload["global_context"]["shell_is_suspect"] is False
    assert payload["focus_component"] == "frame"
    assert payload["claim_boundary"] == "non_promoting_frame_operator_audit_only"


# ---------------------------------------------------------------------------
# reconciliation summary distinguishes consistent vs decorrelated total config
# ---------------------------------------------------------------------------
def test_reconciliation_summary_identifies_configs():
    drv = _load("run_g1_frame_operator_reconciliation_audit")
    jv = np.array([5.0, -1.0, 2.0, 0.0])
    orth = np.array([0.0, 0.0, 0.0, 7.0])
    blocks = {
        "service_real": {"elastic": jv.copy(), "material": jv.copy(),
                         "geometric_delta": np.zeros(4), "total": jv.copy()},
        "placeholder_1mpa": {"elastic": jv.copy(), "material": 1e-6 * jv,
                             "geometric_delta": np.zeros(4), "total": orth},
    }
    payload = drv.build_frame_audit_report(j_frame_v=jv, blocks_by_service=blocks)
    rs = payload["reconciliation_summary"]
    assert "service_real" in rs["service_tangent_configs_reconciling_total"]
    assert "placeholder_1mpa" in rs["service_tangent_configs_decorrelated_total"]
    assert rs["j_frame_matches_elastic_block"] is True
    # placeholder/total is flagged as a suspect; service_real/total is not
    suspect_configs = {s["service_tangent"] for s in payload["ranked_frame_suspects"]}
    assert "placeholder_1mpa" in suspect_configs
    assert "service_real" not in suspect_configs


# ---------------------------------------------------------------------------
# 8. frame subcomponent shape mismatch -> ERR_FRAME_COMPONENT_SHAPE_MISMATCH
# ---------------------------------------------------------------------------
def test_frame_subcomponent_shape_mismatch():
    drv = _load("run_g1_frame_operator_reconciliation_audit")
    jv = np.array([1.0, 2.0, 3.0])
    blocks = {"service_real": {"total": np.array([1.0, 2.0])}}  # wrong shape
    payload = drv.build_frame_audit_report(j_frame_v=jv, blocks_by_service=blocks)
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == "ERR_FRAME_COMPONENT_SHAPE_MISMATCH"
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 7. missing MGT input -> fail-closed reason code
# ---------------------------------------------------------------------------
def test_missing_mgt_input(tmp_path):
    drv = _load("run_g1_frame_operator_reconciliation_audit")
    payload = drv.run_g1_frame_operator_reconciliation_audit(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["reason_code"] == drv.ERR_MGT_INPUT_MISSING
    assert payload["promotes_g1_closure"] is False
    assert str(drv.DEFAULT_OUTPUT_JSON).endswith(".local.json")
