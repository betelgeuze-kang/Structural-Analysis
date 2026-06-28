"""Hermetic tests for F2g-alt: null-space mode audit.

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


# ---------------------------------------------------------------------------
# 1 + 2. diagonal scan detects zero and tiny rows
# ---------------------------------------------------------------------------
def test_scan_diagonal_zero_and_tiny():
    aud = _load("g1_null_space_audit")
    diag = np.array([0.0, 1.0e-12, 5.0, 1.0e9])
    stats = aud.scan_diagonal(diag, floor=1.0e-8)
    assert stats["zero_diag_count"] == 1
    assert stats["tiny_diag_count"] == 2  # 0.0 and 1e-12 both < floor
    assert stats["diag_max_abs"] == 1.0e9


# ---------------------------------------------------------------------------
# 3. mode maps free dof -> node / dof type
# ---------------------------------------------------------------------------
def test_map_mode_to_dofs():
    aud = _load("g1_null_space_audit")
    # 2 nodes, 6 dof each; free = all 12; node ids [101, 202]
    free = np.arange(12)
    node_id = np.array([101, 202])
    z = np.zeros(12)
    z[8] = 1.0  # global dof 8 -> node 1 (202), comp 2 -> UZ
    mapped = aud.map_mode_to_dofs(z, free, node_id, 6, top=1)
    top = mapped["dominant_nodes"][0]
    assert top["node_id"] == 202
    assert top["dof"] == "UZ"
    assert mapped["dominant_dof_types"]["UZ"] == 1.0


# ---------------------------------------------------------------------------
# 4 + 5. classification
# ---------------------------------------------------------------------------
def test_classify_drilling():
    aud = _load("g1_null_space_audit")
    assert aud.classify_mode({"RZ": 0.8, "UY": 0.2}) == aud.CLASS_DRILLING


def test_classify_translation():
    aud = _load("g1_null_space_audit")
    assert aud.classify_mode({"UX": 0.5, "UY": 0.4, "RZ": 0.1}) == aud.CLASS_TRANSLATION


def test_classify_unrestrained_rotation():
    aud = _load("g1_null_space_audit")
    assert aud.classify_mode({"RX": 0.4, "RY": 0.3, "UZ": 0.3}) == aud.CLASS_UNRESTRAINED_ROTATION


# ---------------------------------------------------------------------------
# 10. dominant_dof_types normalizes to ~1 over present types
# ---------------------------------------------------------------------------
def test_dominant_dof_types_normalized():
    aud = _load("g1_null_space_audit")
    rng = np.random.default_rng(0)
    free = np.arange(18)
    node_id = np.array([1, 2, 3])
    z = rng.standard_normal(18)
    mapped = aud.map_mode_to_dofs(z, free, node_id, 6)
    assert abs(sum(mapped["dominant_dof_types"].values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 9. pinning candidates are candidate_only_not_applied
# ---------------------------------------------------------------------------
def test_pinning_candidates_not_applied():
    aud = _load("g1_null_space_audit")
    rows = [{"dominant_dof_types": {"RZ": 0.8, "UY": 0.2}},
            {"dominant_dof_types": {"RZ": 0.7, "UX": 0.3}}]
    cands = aud.aggregate_pinning_candidates(rows)
    assert cands[0]["target_dof_type"] == "RZ"
    assert cands[0]["candidate_count"] == 2
    assert all(c["claim_boundary"] == "candidate_only_not_applied" for c in cands)


def test_aggregate_empty():
    aud = _load("g1_null_space_audit")
    assert aud.aggregate_pinning_candidates([]) == []


# ---------------------------------------------------------------------------
# end-to-end report core (small synthetic matrix)
# ---------------------------------------------------------------------------
def _small_spd_csr(n=12, seed=2):
    rng = np.random.default_rng(seed)
    raw = rng.standard_normal((n, n))
    return csr_matrix(raw @ raw.T + n * np.eye(n))


def test_report_scan_only_non_promoting():
    drv = _load("run_g1_null_space_mode_audit")
    k = _small_spd_csr()
    payload = drv.build_null_space_report(
        k_free=k, free=np.arange(12), node_id=np.array([1, 2]), dof_per_node=6,
        scan_only=True,
    )
    assert payload["promotes_g1_closure"] is False
    assert payload["reason_code"] == drv.PASS
    assert payload["singularity_indicators"]["smallest_eigen_attempted"] is False
    assert payload["claim_boundary"] == "non_promoting_null_space_audit_only"


def test_report_eigen_modes():
    drv = _load("run_g1_null_space_mode_audit")
    k = _small_spd_csr()
    payload = drv.build_null_space_report(
        k_free=k, free=np.arange(12), node_id=np.array([1, 2]), dof_per_node=6, max_modes=4,
    )
    assert payload["status"] == "ready"
    assert len(payload["mode_rows"]) == 4
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 7. eigen failure -> fail-closed reason
# ---------------------------------------------------------------------------
def test_eigen_failure_fail_closed(monkeypatch):
    drv = _load("run_g1_null_space_mode_audit")
    k = _small_spd_csr()

    def boom(*a, **k):
        raise RuntimeError("eigsh blew up")

    monkeypatch.setattr(drv, "eigsh", boom)
    payload = drv.build_null_space_report(
        k_free=k, free=np.arange(12), node_id=np.array([1, 2]), dof_per_node=6, max_modes=4,
    )
    assert payload["reason_code"] == drv.ERR_EIGEN_SOLVE_FAILED
    assert payload["promotes_g1_closure"] is False


# ---------------------------------------------------------------------------
# 8. missing mgt input fail-closed, non-promoting
# ---------------------------------------------------------------------------
def test_missing_mgt_input(tmp_path):
    drv = _load("run_g1_null_space_mode_audit")
    payload = drv.run_g1_null_space_mode_audit(
        mgt_model=tmp_path / "missing.mgt", output_json=tmp_path / "o.local.json",
    )
    assert payload["reason_code"] == drv.ERR_MGT_INPUT_MISSING
    assert payload["promotes_g1_closure"] is False
    assert str(drv.DEFAULT_OUTPUT_JSON).endswith(".local.json")
