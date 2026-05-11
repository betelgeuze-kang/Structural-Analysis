from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
IFC_SCRIPT = REPO_ROOT / "implementation/phase1/convert_ifc_private_corpus_to_structural_graph.py"
QUEUE_SCRIPT = REPO_ROOT / "implementation/phase1/build_real_drawing_optimization_intake_queue.py"
IFC_SPEC = importlib.util.spec_from_file_location("convert_ifc_private_corpus_to_structural_graph", IFC_SCRIPT)
assert IFC_SPEC is not None and IFC_SPEC.loader is not None
ifc_adapter = importlib.util.module_from_spec(IFC_SPEC)
IFC_SPEC.loader.exec_module(ifc_adapter)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _manifest_payload(private_path: Path | None = None) -> dict:
    file_row = {
        "file_id": "fixture_ifc",
        "file_name": "fixture.ifc",
        "file_type": ".ifc",
        "role": "bim_ifc_model",
        "bytes": 321,
        "sha256": "abc123",
        "source_url": "https://example.invalid/fixture.ifc",
        "model_optimization_candidate": True,
        "raw_redistribution_allowed": False,
        "release_surface_allowed": False,
    }
    if private_path is not None:
        file_row["private_path"] = str(private_path)
    return {
        "schema_version": "real-drawing-private-corpus-manifest.v1",
        "projects": [
            {
                "project_id": "fixture_project",
                "project_title": "Fixture Project",
                "source_family": "fixture",
                "files": [file_row],
            }
        ],
    }


def test_ifc_adapter_builds_proxy_graph_and_omits_private_path(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private" / "fixture.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#10= IFCBUILDINGSTOREY('storey-guid',$,'Level 1',$,$,$,$,$,$);
#20= IFCCOLUMN('column-guid',$,'C1',$,$,$,$,$);
#21= IFCBEAM('beam-guid',$,'B1',$,$,$,$,$);
#22= IFCSLAB('slab-guid',$,'S1',$,$,$,$,$);
#30= IFCRELCONTAINEDINSPATIALSTRUCTURE('rel-guid',$,$,$,(#20,#21,#22),#10);
ENDSEC;
END-ISO-10303-21;
""",
        encoding="utf-8",
    )
    private_manifest = tmp_path / "private_manifest.json"
    redacted_manifest = tmp_path / "redacted_manifest.json"
    out_dir = tmp_path / "ifc_adapter"
    _write_json(private_manifest, _manifest_payload(private_path=ifc_path))
    _write_json(redacted_manifest, _manifest_payload(private_path=None))

    proc = subprocess.run(
        [
            sys.executable,
            str(IFC_SCRIPT),
            "--private-manifest",
            str(private_manifest),
            "--redacted-manifest",
            str(redacted_manifest),
            "--out-dir",
            str(out_dir),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    report_text = (out_dir / "fixture_ifc.report.json").read_text(encoding="utf-8")
    graph = json.loads((out_dir / "fixture_ifc.graph.json").read_text(encoding="utf-8"))
    report = json.loads(report_text)
    assert "private_path" not in report_text
    assert str(ifc_path) not in report_text
    assert report["adapter_mode"] == "entity_proxy_graph"
    assert report["contract_pass"] is True
    assert report["solver_exact"] is False
    assert "material/section binding" in report["readiness_note"]
    assert report["metrics"]["structural_entity_count"] == 3
    assert report["entity_counts"]["IFCBUILDINGSTOREY"] == 1
    assert report["entity_counts"]["IFCCOLUMN"] == 1
    assert graph["metrics"]["proxy_node_count"] == 4
    assert graph["metrics"]["proxy_edge_count"] == 3


def test_ifc_adapter_uses_release_safe_aggregate_group_edges(tmp_path: Path) -> None:
    ifc_path = tmp_path / "private" / "aggregate_only.ifc"
    ifc_path.parent.mkdir(parents=True)
    ifc_path.write_text(
        """ISO-10303-21;
HEADER;
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
#5= IFCBUILDING('building-guid',$,'Building',$,$,$,$,$,$,$,$,$);
#6= IFCCARTESIANPOINT((10.,20.,0.));
#7= IFCAXIS2PLACEMENT3D(#6,$,$);
#8= IFCLOCALPLACEMENT($,#7);
#9= IFCCARTESIANPOINT((14.,22.,0.));
#10= IFCAXIS2PLACEMENT3D(#9,$,$);
#11= IFCLOCALPLACEMENT($,#10);
#20= IFCCOLUMN('column-guid',$,'C1',$,$,#8,$,$);
#21= IFCBEAM('beam-guid',$,'B1',$,$,#11,$,$);
#30= IFCRELAGGREGATES('rel-guid',$,$,$,#5,(#20,#21));
ENDSEC;
END-ISO-10303-21;
""",
        encoding="utf-8",
    )

    payload = ifc_adapter.parse_ifc_proxy_graph(ifc_path)

    assert payload["metrics"]["structural_entity_count"] == 2
    assert payload["metrics"]["direct_relationship_edge_count"] == 0
    assert payload["metrics"]["relationship_group_node_count"] == 1
    assert payload["metrics"]["proxy_node_count"] == 3
    assert payload["metrics"]["proxy_edge_count"] == 2
    assert payload["metrics"]["placement_coordinate_structural_count"] == 2
    assert payload["metrics"]["placement_coordinate_node_count"] == 3
    assert payload["evidence_receipts"]["ifc_local_placement_coordinate_extraction_receipt"]["contract_pass"] is True
    assert payload["proxy_relationship_counts"] == {"aggregates_decomposition": 2}
    assert "release_safe_aggregate_group_edges" in payload["relationship_extraction_modes"]
    assert next(node for node in payload["nodes"] if node["id"] == "#20")["x"] == 10.0
    assert next(node for node in payload["nodes"] if node["id"] == "#21")["y"] == 22.0
    group_node = next(node for node in payload["nodes"] if node["id"] == "relationship:IFCRELAGGREGATES:#30")
    assert group_node["x"] == 12.0
    assert group_node["y"] == 21.0
    assert all(edge["target"] == "relationship:IFCRELAGGREGATES:#30" for edge in payload["edges"])


def test_queue_promotes_ifc_adapter_report_to_proxy_ready(tmp_path: Path) -> None:
    manifest = tmp_path / "redacted_manifest.json"
    mgt_parse_dir = tmp_path / "mgt_parse"
    ifc_adapter_dir = tmp_path / "ifc_adapter"
    out = tmp_path / "queue.json"
    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "fixture_project",
                    "project_title": "Fixture Project",
                    "source_family": "fixture",
                    "files": [
                        {
                            "file_id": "fixture_ifc",
                            "file_name": "fixture.ifc",
                            "file_type": ".ifc",
                            "role": "bim_ifc_model",
                            "bytes": 321,
                            "sha256": "abc123",
                            "source_url": "https://example.invalid/fixture.ifc",
                            "model_optimization_candidate": True,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        ifc_adapter_dir / "fixture_ifc.report.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "adapter_mode": "entity_proxy_graph",
            "solver_exact": False,
            "graph_json": str(ifc_adapter_dir / "fixture_ifc.graph.json"),
            "metrics": {
                "proxy_node_count": 4,
                "proxy_edge_count": 3,
                "structural_entity_count": 3,
                "storey_count": 1,
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(QUEUE_SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--mgt-parse-report-dir",
            str(mgt_parse_dir),
            "--ifc-adapter-report-dir",
            str(ifc_adapter_dir),
            "--out",
            str(out),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["optimized_drawing_generation_ready_count"] == 1
    assert payload["summary"]["ifc_proxy_graph_ready_count"] == 1
    assert payload["summary"]["ifc_adapter_required_count"] == 0
    assert payload["summary"]["ready_ifc_proxy_node_count_total"] == 4
    row = payload["queue"][0]
    assert row["optimization_status"] == "ifc_proxy_graph_ready"
    assert row["ready_for_optimized_drawing_generation"] is True
    assert row["solver_exact"] is False
    assert "not solver-exact" in row["readiness_note"]
    assert "load extraction" in row["readiness_note"]
