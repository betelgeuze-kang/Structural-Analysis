from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "implementation/phase1/build_real_drawing_ifc_solver_exact_reconstruction_plan.py"
SPEC = importlib.util.spec_from_file_location("build_real_drawing_ifc_solver_exact_reconstruction_plan", SCRIPT_PATH)
assert SPEC is not None
reconstruction_plan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(reconstruction_plan)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fixture_inputs(tmp_path: Path) -> tuple[Path, Path]:
    report_dir = tmp_path / "ifc_adapter"
    rows = [
        ("fixture_a", 0, 3, ["proxy_layout_not_true_geometry", "proxy_node_glyph_fallback", "not_solver_exact"]),
        ("fixture_b", 2, 3, ["proxy_layout_not_true_geometry", "not_solver_exact"]),
        ("fixture_c", 3, 3, ["proxy_layout_not_true_geometry", "not_solver_exact"]),
    ]
    queue_rows = []
    viewer_assets = []
    for index, (stem, edges, structural, flags) in enumerate(rows, start=1):
        graph_path = report_dir / f"{stem}.graph.json"
        report_path = report_dir / f"{stem}.report.json"
        edge_rows = [
            {"source": f"#{edge_index}", "target": "#99", "relationship": "contained_in_spatial_structure"}
            for edge_index in range(edges)
        ]
        _write_json(
            graph_path,
            {
                "metrics": {
                    "proxy_node_count": structural + 1,
                    "proxy_edge_count": edges,
                    "structural_entity_count": structural,
                    "storey_count": 1,
                },
                "evidence_receipts": (
                    {
                        "ifc_local_placement_coordinate_extraction_receipt": {
                            "contract_pass": True,
                            "reason_code": "PASS_IFC_LOCAL_PLACEMENT_COORDINATES_EXTRACTED",
                            "placement_coverage_ratio": 1.0,
                        }
                    }
                    if stem == "fixture_c"
                    else {}
                ),
                "edges": edge_rows,
            },
        )
        _write_json(
            report_path,
            {
                "contract_pass": True,
                "graph_json": str(graph_path),
                "metrics": {
                    "proxy_node_count": structural + 1,
                    "proxy_edge_count": edges,
                    "structural_entity_count": structural,
                    "storey_count": 1,
                },
                "source_url": "SHOULD_NOT_LEAK",
            },
        )
        queue_rows.append(
            {
                "file_id": f"{stem}_ifc",
                "file_type": ".ifc",
                "source_url": "SHOULD_NOT_LEAK",
                "ifc_adapter_report": str(report_path),
                "ifc_proxy_graph_json": str(graph_path),
                "optimization_route": "ifc_to_structural_graph_adapter",
                "optimization_status": "ifc_proxy_graph_ready",
                "ready_for_optimized_drawing_generation": True,
                "solver_exact": False,
            }
        )
        viewer_assets.append(
            {
                "asset_ref": f"RD-{index:03d}",
                "file_type": ".ifc",
                "route": "ifc_to_structural_graph_adapter",
                "status": "ifc_proxy_graph_ready",
                "solver_exact": False,
                "quality_flags": flags,
            }
        )
    viewer_manifest = _write_json(tmp_path / "viewer_manifest.json", {"assets": viewer_assets})
    intake_queue = _write_json(tmp_path / "model_optimization_intake_queue.json", {"queue": queue_rows})
    return viewer_manifest, intake_queue


def test_ifc_reconstruction_plan_classifies_proxy_blockers_and_omits_source_urls(tmp_path: Path) -> None:
    viewer_manifest, intake_queue = _fixture_inputs(tmp_path)

    report = reconstruction_plan.build_reconstruction_plan(viewer_manifest, intake_queue)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS_IFC_RECONSTRUCTION_PLAN_OPEN"
    assert report["summary"]["ifc_asset_count"] == 3
    assert report["summary"]["blocked_count"] == 3
    assert report["summary"]["node_glyph_fallback_count"] == 1
    assert report["summary"]["relationship_coverage_gap_count"] == 1
    assert report["summary"]["geometry_material_load_adapter_required_count"] == 1
    assert report["summary"]["local_placement_receipt_count"] == 1
    assert report["ifc_reconstruction_items"][0]["blocker_reason_code"] == "ERR_IFC_PROXY_NODE_GLYPH_FALLBACK"
    assert report["ifc_reconstruction_items"][1]["blocker_reason_code"] == "ERR_IFC_PROXY_RELATIONSHIP_COVERAGE_GAP"
    assert report["ifc_reconstruction_items"][2]["blocker_reason_code"] == "ERR_IFC_PROXY_LAYOUT_NOT_TRUE_GEOMETRY"
    assert report["ifc_reconstruction_items"][1]["metrics"]["edge_coverage_ratio"] == 0.6667
    assert report["ifc_reconstruction_items"][2]["attached_evidence"] == [
        "ifc_local_placement_coordinate_extraction_receipt"
    ]
    assert "ifc_local_placement_coordinate_extraction_receipt" not in report["ifc_reconstruction_items"][2]["open_evidence"]
    assert "ifc_relationship_edge_extraction_receipt" in report["ifc_reconstruction_items"][0]["required_evidence"]
    assert "SHOULD_NOT_LEAK" not in json.dumps(report)


def test_ifc_reconstruction_plan_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    viewer_manifest, intake_queue = _fixture_inputs(tmp_path)
    out_path = tmp_path / "plan.json"
    out_md_path = tmp_path / "plan.md"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--viewer-manifest",
            str(viewer_manifest),
            "--intake-queue",
            str(intake_queue),
            "--out",
            str(out_path),
            "--out-md",
            str(out_md_path),
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"]["ifc_asset_count"] == 3
    assert json.loads(out_path.read_text(encoding="utf-8"))["summary"]["blocked_count"] == 3
    assert "Real Drawing IFC Solver-Exact Reconstruction Plan" in out_md_path.read_text(encoding="utf-8")
