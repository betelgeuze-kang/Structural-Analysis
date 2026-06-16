from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_opensees_roundtrip_trace_report.py"
SPEC = importlib.util.spec_from_file_location("build_opensees_roundtrip_trace_report", SCRIPT_PATH)
assert SPEC is not None
build_opensees_roundtrip_trace_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_opensees_roundtrip_trace_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_opensees_roundtrip_trace_report_passes_exact_reload(tmp_path: Path) -> None:
    edges = _write(
        tmp_path / "edges.json",
        {
            "schema_version": "1.0",
            "node_count": 3,
            "source": "model.tcl",
            "edges": [[2, 1], [0, 1]],
        },
    )
    topology = _write(
        tmp_path / "topology.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "inputs": {"model": "model.tcl"},
            "source_provenance": {"source_path": "model.tcl", "source_sha256": "abc"},
            "metrics": {"node_count": 3, "edge_count_undirected": 2},
            "artifacts": {"edges_json": str(edges)},
        },
    )

    report, canonical = build_opensees_roundtrip_trace_report.build_report(
        topology_path=topology,
        canonical_out=tmp_path / "canonical.json",
    )

    assert report["contract_pass"] is True
    assert report["summary"]["roundtrip_exact_entry_row_coverage_min"] == 1.0
    assert canonical["edges"] == [[0, 1], [1, 2]]


def test_opensees_roundtrip_trace_report_blocks_count_mismatch(tmp_path: Path) -> None:
    edges = _write(
        tmp_path / "edges.json",
        {"node_count": 3, "source": "model.tcl", "edges": [[0, 1]]},
    )
    topology = _write(
        tmp_path / "topology.json",
        {
            "contract_pass": True,
            "inputs": {"model": "model.tcl"},
            "source_provenance": {"source_path": "model.tcl"},
            "metrics": {"node_count": 3, "edge_count_undirected": 2},
            "artifacts": {"edges_json": str(edges)},
        },
    )

    report, _ = build_opensees_roundtrip_trace_report.build_report(
        topology_path=topology,
        canonical_out=tmp_path / "canonical.json",
    )

    assert report["contract_pass"] is False
    assert "edge_count_match" in report["blockers"]
