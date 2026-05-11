from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/build_real_drawing_private_3d_webviewer.py"
    )
    spec = importlib.util.spec_from_file_location("build_real_drawing_private_3d_webviewer", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_private_3d_webviewer_builds_sanitized_asset_registry(tmp_path: Path) -> None:
    module = _load_module()
    graph_dir = tmp_path / "graphs"
    mgt_graph = graph_dir / "solver.json"
    ifc_graph = graph_dir / "proxy.graph.json"
    queue_path = tmp_path / "model_optimization_intake_queue.json"
    promotion_queue_path = tmp_path / "solver_exact_promotion_queue.json"
    out_html = tmp_path / "webviewer" / "real_drawing_3d_registry.html"
    out_summary = tmp_path / "webviewer" / "real_drawing_3d_registry_summary.json"
    out_sidecar = tmp_path / "structure-viewer" / "index.real_drawing_private.data.js"

    _write_json(
        mgt_graph,
        {
            "schema_version": "fixture",
            "source": {"private_path": "SHOULD_NOT_LEAK_SOURCE"},
            "model": {
                "nodes": [
                    {"id": 1, "x": 0, "y": 0, "z": 0},
                    {"id": 2, "x": 10, "y": 0, "z": 0},
                    {"id": 3, "x": 10, "y": 5, "z": 0},
                ],
                "elements": [
                    {"id": 1, "type": "BEAM", "family": "beam", "node_ids": [1, 2]},
                    {"id": 2, "type": "PLATE", "family": "plate", "node_ids": [1, 2, 3]},
                ],
            },
        },
    )
    _write_json(
        ifc_graph,
        {
            "schema_version": "fixture",
            "source": {"source_url": "https://SHOULD_NOT_LEAK.example/ifc"},
            "nodes": [
                {"id": "#1", "ifc_entity_type": "IFCBUILDINGSTOREY", "proxy_node_kind": "storey"},
                {"id": "#2", "ifc_entity_type": "IFCBEAM", "proxy_node_kind": "structural_entity"},
            ],
            "edges": [{"source": "#2", "target": "#1", "relationship": "contained_in_spatial_structure"}],
        },
    )
    _write_json(
        queue_path,
        {
            "contract_pass": True,
            "queue": [
                {
                    "file_id": "SHOULD_NOT_LEAK_FILE_ID",
                    "file_name": "SHOULD_NOT_LEAK_MODEL.mgt",
                    "source_url": "https://SHOULD_NOT_LEAK.example/model.mgt",
                    "private_path": "/private/SHOULD_NOT_LEAK/model.mgt",
                    "source_private_manifest": "SHOULD_NOT_LEAK_MANIFEST",
                    "solver_graph_model_json": str(mgt_graph),
                    "file_type": ".mgt",
                    "optimization_route": "midas_mgt_direct_parser",
                    "optimization_status": "solver_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": True,
                    "model_asset_count": 1,
                },
                {
                    "file_id": "SHOULD_NOT_LEAK_IFC_ID",
                    "file_name": "SHOULD_NOT_LEAK.ifc",
                    "source_url": "https://SHOULD_NOT_LEAK.example/model.ifc",
                    "ifc_proxy_graph_json": str(ifc_graph),
                    "file_type": ".ifc",
                    "optimization_route": "ifc_to_structural_graph_adapter",
                    "optimization_status": "ifc_proxy_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": False,
                    "model_asset_count": 1,
                },
            ],
        },
    )
    _write_json(
        promotion_queue_path,
        {
            "contract_pass": True,
            "summary": {
                "current_solver_exact_asset_count": 1,
                "target_solver_exact_asset_count": 2,
                "required_solver_exact_delta": 1,
                "planned_unlock_batch_count": 1,
                "planned_solver_exact_asset_count_after_unlock_batch": 2,
            },
            "planned_unlock_batch": [
                {
                    "promotion_id": "RP-001",
                    "asset_ref": "RD-002",
                    "promotion_family": "ifc_coordinate_geometry_reconstruction",
                    "expected_solver_exact_delta": 1,
                    "recommended_action": "replace proxy layout with recovered structural geometry",
                    "source_url": "https://SHOULD_NOT_LEAK.example/promotion",
                }
            ],
        },
    )

    summary = module.build_webviewer(
        intake_queue_path=queue_path,
        out_html=out_html,
        out_summary=out_summary,
        out_viewer_sidecar=out_sidecar,
        promotion_queue_path=promotion_queue_path,
        max_segments_per_asset=20,
        max_proxy_nodes=20,
        max_proxy_edges=20,
    )

    assert summary["schema_version"] == "real-drawing-private-3d-webviewer.v1"
    assert summary["asset_count"] == 2
    assert summary["renderable_asset_count"] == 2
    assert summary["solver_exact_asset_count"] == 1
    assert summary["proxy_or_preview_asset_count"] == 1
    assert summary["structure_viewer_preset"] == "real_drawing_private_3d"
    assert summary["structure_viewer_href"] == "src/structure-viewer/index.html?preset=real_drawing_private_3d"
    assert summary["solver_exact_promotion_queue"] == str(promotion_queue_path)
    assert summary["solver_exact_target_asset_count"] == 2
    assert summary["solver_exact_planned_unlock_batch_count"] == 1
    assert out_html.exists()
    assert out_summary.exists()
    assert out_sidecar.exists()
    html_text = out_html.read_text(encoding="utf-8")
    summary_text = out_summary.read_text(encoding="utf-8")
    sidecar_text = out_sidecar.read_text(encoding="utf-8")
    assert "RD-001" in html_text
    assert "RD-002" in html_text
    assert "solver_topology_xyz" in html_text
    assert "ifc_proxy_topology_3d_layout" in html_text
    assert "window.__STRUCTURE_VIEWER_PRESET_PAYLOADS__=" in sidecar_text
    assert "real_drawing_private_3d" in sidecar_text
    assert "Real Drawing Private 3D Gallery" in sidecar_text
    assert "real_drawing_solver_exact_promotion_queue" in sidecar_text
    assert "RP-001" in sidecar_text
    assert "IFC proxy topology layout" in sidecar_text
    assert "private local derived topology sidecar" in sidecar_text
    for token in (
        "SHOULD_NOT_LEAK",
        "source_url",
        "private_path",
        "source_private_manifest",
        "file_name",
        "file_id",
    ):
        assert token not in html_text
        assert token not in summary_text
        assert token not in sidecar_text


def test_private_3d_webviewer_keeps_solver_exact_compact_archive_out_of_sparse_review(tmp_path: Path) -> None:
    module = _load_module()
    graph_path = tmp_path / "graphs" / "compact_archive.json"
    queue_path = tmp_path / "model_optimization_intake_queue.json"
    _write_json(
        graph_path,
        {
            "model": {
                "nodes": [
                    {"id": 1, "x": 0, "y": 0, "z": 0},
                    {"id": 2, "x": 1, "y": 0, "z": 0},
                    {"id": 3, "x": 1, "y": 1, "z": 0},
                ],
                "elements": [{"id": 1, "family": "beam", "node_ids": [1, 2, 3]}],
            }
        },
    )
    _write_json(
        queue_path,
        {
            "queue": [
                {
                    "solver_graph_model_json": str(graph_path),
                    "file_type": ".zip",
                    "optimization_route": "midas_binary_archive_exact_topology_promoted",
                    "optimization_status": "archive_solver_graph_ready",
                    "ready_for_optimized_drawing_generation": True,
                    "solver_exact": True,
                    "model_asset_count": 1,
                }
            ]
        },
    )

    registry = module.build_registry_payload(
        intake_queue_path=queue_path,
        max_segments_per_asset=20,
    )

    asset = registry["assets"][0]
    assert asset["solver_exact"] is True
    assert asset["segment_count"] == 3
    assert "sparse_preview" not in asset["quality_flags"]
    assert asset["warning_label"] == ""
