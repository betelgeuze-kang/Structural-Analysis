from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from implementation.phase1 import gnn_residual_model as model
from implementation.phase1 import lf_to_gnn_e2e_smoke as smoke
from implementation.phase1.validate_phase1_artifacts import validate_smoke


def _nodes() -> list[dict]:
    return [
        {"node_id": "N1", "ux": 0.1, "uy": 0.2, "uz": 0.3, "f_norm": 100.0},
        {"node_id": "N2", "ux": 0.3, "uy": 0.2, "uz": 0.1, "f_norm": 100.0},
    ]


def _assert_unavailable(metrics: dict) -> None:
    for key in ("physical_accuracy_pct", "residual_l1_before", "residual_l1_after", "residual_reduction_ratio"):
        assert metrics[key] is None
    assert metrics["solver_recomputed"] is False
    assert metrics["physical_metrics_status"] == "unavailable"
    assert metrics["physical_metrics_reason_code"] == "ERR_LF_GNN_PHYSICAL_METRICS_UNAVAILABLE"
    assert metrics["target_met"] is False
    assert metrics["learned_parameters"] is False
    json.dumps(metrics, allow_nan=False)


@pytest.mark.parametrize("gain", [0.0, 0.001])
def test_scalar_contraction_never_becomes_physical_accuracy(gain: float) -> None:
    nodes = _nodes()
    corrected, metrics = model.run_one_batch_with_metrics(
        nodes, [{"from": "N1", "to": "N2"}],
        {"physical_accuracy_pct": 100.0, "solver_recomputed": True}, gain=gain,
    )

    assert metrics["heuristic_state_reduction_ratio"] > 0.999
    assert metrics["algorithm_kind"] == "fixed_coefficient_graph_heuristic"
    _assert_unavailable(metrics)
    if gain == 0.0:
        assert corrected == [{key: row[key] for key in ("node_id", "ux", "uy", "uz")} for row in nodes]
    else:
        assert corrected[0]["ux"] != nodes[0]["ux"]


def test_fixed_nodes_do_not_gain_accuracy_when_internal_scalars_contract() -> None:
    nodes = [{**row, "bc_type": "fixed"} for row in _nodes()]
    corrected, metrics = model.run_one_batch_with_metrics(nodes, [{"from": "N1", "to": "N2"}], {}, gain=1.0)

    assert corrected == [{key: row[key] for key in ("node_id", "ux", "uy", "uz")} for row in nodes]
    assert metrics["heuristic_state_reduction_ratio"] > 0.999
    _assert_unavailable(metrics)


@pytest.mark.parametrize("nodes", [[], [{"node_id": "N1", "ux": 0.0, "uy": 0.0, "uz": 0.0}]])
def test_empty_or_zero_input_is_not_physics_evidence(nodes: list[dict]) -> None:
    _, metrics = model.run_one_batch_with_metrics(nodes, [], {}, gain=0.0)

    _assert_unavailable(metrics)


@pytest.mark.parametrize("target_accuracy_pct", [0.0, 99.9])
@pytest.mark.parametrize("fallback", [False, True])
def test_smoke_does_not_reconstruct_accuracy_from_internal_scalars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_accuracy_pct: float, fallback: bool,
) -> None:
    monkeypatch.setitem(sys.modules, "gnn_residual_model", None if fallback else model)
    monkeypatch.setitem(sys.modules, "torch", None)
    nodes = tmp_path / "nodes.csv"
    nodes.write_text("node_id,ux,uy,uz,f_norm\nN1,0.1,0.2,0.3,100\nN2,0.3,0.2,0.1,100\n", encoding="utf-8")
    edges = tmp_path / "edges.csv"
    edges.write_text("from,to\nN1,N2\n", encoding="utf-8")
    meta = tmp_path / "meta.json"
    meta.write_text('{"unit_system":"SI"}', encoding="utf-8")

    report = smoke.run(nodes, edges, meta, batch_size=2, gain=0.0, target_accuracy_pct=target_accuracy_pct)

    _assert_unavailable(report["inference"])
    if not fallback:
        assert report["inference"]["heuristic_state_reduction_ratio"] > 0.999
    assert report["inference"]["fallback_used"] is fallback
    assert report["inference"]["backend"] == "python"
    assert report["inference"]["residual_correction_applied"] is False
    assert report["pass"] is False
    assert report["reason_code"] == "ERR_LF_GNN_PHYSICAL_METRICS_UNAVAILABLE"
    assert validate_smoke(report) == []


def test_fallback_cannot_claim_physical_accuracy_even_with_large_gain() -> None:
    _, metrics = smoke._apply_residual_batch_fallback(_nodes(), gain=100.0)

    assert metrics["heuristic_state_reduction_ratio"] > 0.999
    assert metrics["algorithm_kind"] == "fixed_coefficient_displacement_heuristic"
    _assert_unavailable(metrics)
